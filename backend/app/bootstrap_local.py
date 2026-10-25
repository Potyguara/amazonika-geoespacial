from __future__ import annotations

import argparse
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.auth import Permission, Role, User


PERMISSIONS = {
    "users.manage": ("Gerenciar usuários e áreas autorizadas", "users"),
    "sources.view": ("Visualizar fontes de dados", "sources"),
    "sources.import": ("Importar dados geoespaciais", "sources"),
    "sources.manage": ("Gerenciar fontes de dados", "sources"),
    "analysis.view": ("Visualizar análises", "analysis"),
    "analysis.execute": ("Executar análises e ferramentas geoespaciais", "analysis"),
    "analysis.export": ("Exportar análises", "analysis"),
}

ROLE_PERMISSIONS = {
    "ADMINISTRADOR": set(PERMISSIONS),
    "ANALISTA": {
        "sources.view",
        "analysis.view",
        "analysis.execute",
        "analysis.export",
    },
}


def get_or_create_permission(db, code: str) -> Permission:
    permission = db.scalar(select(Permission).where(Permission.code == code))
    if permission:
        return permission

    name, module = PERMISSIONS[code]
    permission = Permission(code=code, name=name, module=module)
    db.add(permission)
    db.flush()
    return permission


def get_or_create_role(db, code: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if not role:
        role = Role(
            code=code,
            name="Administrador" if code == "ADMINISTRADOR" else "Analista",
        )
        db.add(role)
        db.flush()

    permissions = [
        get_or_create_permission(db, permission_code)
        for permission_code in sorted(ROLE_PERMISSIONS[code])
    ]
    role.permissions = permissions
    return role


def bootstrap(email: str, full_name: str, password: str) -> None:
    normalized_email = email.strip().lower()
    if len(password) < 12:
        raise SystemExit("A senha precisa ter pelo menos 12 caracteres.")

    with SessionLocal() as db:
        admin_role = get_or_create_role(db, "ADMINISTRADOR")
        get_or_create_role(db, "ANALISTA")

        user = db.scalar(select(User).where(User.email == normalized_email))
        created = user is None

        if user is None:
            user = User(
                email=normalized_email,
                full_name=full_name.strip(),
                password_hash=hash_password(password),
                is_active=True,
                roles=[admin_role],
            )
            db.add(user)
        else:
            user.full_name = full_name.strip()
            user.password_hash = hash_password(password)
            user.is_active = True
            user.roles = [admin_role]

        db.commit()

    action = "criada" if created else "atualizada"
    print(f"Conta administrativa local {action}: {normalized_email}")
    print("Perfil: ADMINISTRADOR")
    print("Acesso territorial: sem restrição")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cria/atualiza uma conta ADMINISTRADOR apenas para homologação local."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    bootstrap(args.email, args.name, args.password)
