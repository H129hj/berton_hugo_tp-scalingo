# TP - Deploiement sur Scalingo

Application complete en production : client React/TypeScript, API FastAPI, base PostgreSQL managee, le tout en HTTPS sur Scalingo. Fonctionnalites : inscription, connexion (JWT), CRUD de notes par utilisateur.

## Architecture

```
Navigateur --HTTPS--> App 1 : client React (buildpack Node.js, build Vite, serve -s dist)
Navigateur --HTTPS--> App 2 : API FastAPI (buildpack Python, uvicorn sur $PORT) --SQL--> Addon PostgreSQL Starter 512
```

- Monorepo : `client/` et `api/`. Chaque app Scalingo cible son dossier via `PROJECT_DIR`.
- Le navigateur charge le client, puis appelle l'API directement. Seule l'API parle a la base.
- Conteneurs ephemeres : aucun fichier local n'est persiste, tout est en base.
- `Procfile` de l'API : `web` (uvicorn) et `postdeploy` (`alembic upgrade head`, migrations jouees apres chaque deploiement).

## Lancer en local

```bash
docker compose up -d                              # PostgreSQL
cd api && cp .env.example .env                    # renseigner SECRET_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head && uvicorn app.main:app --reload     # http://localhost:8000/docs
cd ../client && cp .env.example .env && npm install && npm run dev   # http://localhost:5173
```

## Variables d'environnement (sans valeurs)

| Projet | Variable | Role |
|---|---|---|
| API | `SCALINGO_POSTGRESQL_URL` | Fournie par l'addon, lue automatiquement |
| API | `DATABASE_URL` | Base locale / CI (ignoree si l'addon est present) |
| API | `SECRET_KEY` | Signature des JWT (a generer, jamais commitee) |
| API | `CORS_ORIGINS` | URL publique du client |
| API | `PROJECT_DIR` | `api` (Scalingo, monorepo) |
| API | `ACCESS_TOKEN_MINUTES` | Duree de validite du jeton (defaut 60) |
| Client | `VITE_API_URL` | URL publique de l'API, figee au build |
| Client | `PROJECT_DIR` | `client` (Scalingo, monorepo) |

## Deploiement

Voir [DEPLOY.md](DEPLOY.md) : procedure reproductible pas a pas, CI/CD, exploitation (logs, rollback, sauvegardes).

## Cout mensuel

Estimation (a verifier sur le simulateur de prix Scalingo et a remplacer par le reel) :

| Ressource | Quantite | Estimation |
|---|---|---|
| App API, conteneur S | 1 | ~7 EUR/mois |
| App client, conteneur S | 1 | ~7 EUR/mois |
| PostgreSQL Starter 512 | 1 | 7,2 EUR/mois (prix affiche Scalingo) |
| **Total estime** | | **~21 EUR/mois (< 50 EUR/mois du voucher Ynov)** |

Cout reel : le rapport Billing > Consumption est mis a jour chaque nuit a minuit UTC, il affichait "No data" le 17/11/2026 (apps creees ce jour-la). A relever dans quelques jours et a comparer a l'estimation ci-dessus.

## Donnees initiales

`api/seed.py` cree un compte de demo (`demo@example.com`) et deux notes. Il est relancable sans doublon. Sur Scalingo : `scalingo --app hugo-tp-api run --detached python seed.py`, puis lire le resultat avec `scalingo --app hugo-tp-api logs --filter <id one-off>` (sans `--detached`, `run` echoue ici avec "make stdin raw" car il faut un terminal). Le mot de passe vient de `SEED_PASSWORD`, avec une valeur de demo par defaut.

## En cas de panne

Tout ce qui suit a ete joue le 17/11/2026 sur `hugo-tp-api`. `S` veut dire `scalingo --region osc-fr1 --app hugo-tp-api`.

**1. Lire les logs**

```bash
S logs --lines 200
S logs --filter <id du conteneur>     # un one-off ou web-1
```

**2. Panne volontaire : SECRET_KEY supprimee**

```bash
S env-unset SECRET_KEY && S restart
curl -X POST https://hugo-tp-api.osc-fr1.scalingo.io/auth/login ...   # 500
S logs --lines 60                      # RuntimeError: SECRET_KEY est requis
S env-set "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" && S restart
```

Apres la correction le login repond 200. Les anciens jetons ne sont plus valides puisque la cle change, les utilisateurs doivent se reconnecter. Le `/health` reste a 200 pendant la panne : il ne teste que la base, pas la cle.

**3. Rollback**

`S deployments` liste les deploiements. Comme j'ai deploye par archive, je reviens en arriere en redeployant le commit voulu :

```bash
git archive --format=tar.gz --prefix=tp-scalingo/ -o old.tar.gz <sha>
S deploy old.tar.gz
```

Verifie : apres retour sur le commit d'avant le seed, `S run --detached ls` ne montre plus `seed.py`, et `/health` repond 200. Puis redeploiement du dernier commit de la meme facon. Depuis le dashboard, onglet Deploy, on peut aussi redeployer un ancien deploiement.

**4. Sauvegarde et restauration de la base**

```bash
SA="scalingo --region osc-fr1 --app hugo-tp-api --addon <id addon>"   # id : S addons
$SA backups-create
$SA backups
$SA backups-download --output backup.tar.gz
tar xzf backup.tar.gz     # donne un fichier .pgsql
pg_restore --no-owner --no-privileges -d <base de test> <fichier>.pgsql
```

Restauration testee dans un PostgreSQL local jetable (pas en production) : 2 utilisateurs et 3 notes retrouves, comme dans la base de prod. Il faut un `pg_restore` de version 17 : la sauvegarde est faite avec PostgreSQL 17 et le 16 refuse de la lire ("unsupported version (1.16)"). Une seule erreur sans gravite avec un serveur 16 : `SET transaction_timeout` inconnu. Pour restaurer vraiment en prod, ouvrir un tunnel avec `S --addon <id> db-tunnel` et lancer `pg_restore` dessus, mais je ne l'ai pas fait.

**5. Metriques**

`S stats` (et l'onglet Metrics du dashboard). Releve du 17/11 : API 72 MiB sur 256 (pic 82 MiB), client 69 MiB sur 256, CPU a 0 %. La taille S suffit largement.

**6. Couper pour ne plus payer**

```bash
S scale web:0
scalingo --region osc-fr1 --app hugo-tp-client scale web:0
```

## Justification des choix

- Deux apps separees (variante de base du sujet) : builds et deploiements independants, CORS limite au client.
- Hash de mot de passe PBKDF2 (stdlib) et JWT HS256 : peu de dependances pour un TP.
- `serve -s dist` : fallback SPA, un rafraichissement sur `/notes` ne renvoie pas 404.
