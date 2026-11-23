from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.auth import Role, User


def main():
    email = input("E-mail do SUPER_ADMIN: ").strip().lower()
    full_name = input("Nome completo: ").strip()

    if not email or "@" not in email:
        raise SystemExit("E-mail inválido.")

    if not full_name:
        raise SystemExit("Nome obrigatório.")

    password = getpass("Senha: ")
    confirmation = getpass("Confirme a senha: ")

    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")

    if len(password) < 12:
        raise SystemExit("Use uma senha com pelo menos 12 caracteres.")

    db = SessionLocal()

    try:
        role = db.scalar(
            select(Role).where(Role.code == "SUPER_ADMIN")
        )

        if not role:
            raise SystemExit(
                "Perfil SUPER_ADMIN não encontrado. Execute bootstrap_auth primeiro."
            )

        user = db.scalar(
            select(User).where(User.email == email)
        )

        if user:
            user.full_name = full_name
            user.password_hash = hash_password(password)
            user.is_active = True

            if role not in user.roles:
                user.roles.append(role)

            action = "atualizado"
        else:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                is_active=True,
                roles=[role],
            )
            db.add(user)
            action = "criado"

        db.commit()
        db.refresh(user)

        print(f"SUPER_ADMIN {action}: {user.email}")
        print(f"ID: {user.id}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
