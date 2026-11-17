import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Note, User
from app.security import hash_password

EMAIL = "demo@example.com"


def main():
    password = os.environ.get("SEED_PASSWORD", "demo-motdepasse")
    with Session(get_engine()) as db:
        if db.scalar(select(User).where(User.email == EMAIL)):
            print("Seed deja applique, rien a faire")
            return
        user = User(email=EMAIL, password_hash=hash_password(password))
        user.notes = [
            Note(title="Bienvenue", body="Compte de demo cree par seed.py"),
            Note(title="Deuxieme note", body="Les donnees sont dans PostgreSQL"),
        ]
        db.add(user)
        db.commit()
        print("Seed applique : 1 utilisateur, 2 notes")


if __name__ == "__main__":
    main()
