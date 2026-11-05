"""Provision one disposable homologation administrator using password via stdin.

Use ONLY with the isolated rural-homolog Docker Compose stack.
This does not read, copy, or change production users.
"""
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.auth import Permission, Role, User

REQUIRED = {
    "analysis.view": ("Consultar análises", "analysis"),
    "analysis.execute": ("Executar análises", "analysis"),
    "analysis.export": ("Exportar análises", "analysis"),
    "users.manage": ("Gerenciar usuários", "users"),
    "sources.view": ("Consultar fontes", "sources"),
    "sources.manage": ("Gerenciar fontes", "sources"),
}


def main():
    url = engine.url
    if (
        os.getenv("RURAL_HOMOLOG_SEED") != "yes"
        or url.host != "db"
        or url.database != "amazonika_rural_homolog"
        or url.username != "rural_homolog"
    ):
        raise SystemExit("BLOQUEADO: provisionamento permitido somente no banco rural homologado.")
    email = os.environ.get("RURAL_HOMOLOG_ADMIN_EMAIL", "").strip().lower()
    if not email.endswith("@example.com") or len(email) > 120:
        raise SystemExit("Use e-mail de teste do domínio reservado @example.com.")
    password = sys.stdin.readline().rstrip("\r\n")
    if len(password) < 14:
        raise SystemExit("Senha de homologação deve possuir ao menos 14 caracteres.")
    with SessionLocal() as session:
        role = session.scalar(select(Role).where(Role.code == "ADMINISTRADOR"))
        if not role:
            role = Role(code="ADMINISTRADOR", name="Administrador de homologação")
            session.add(role)
            session.flush()
        permissions = []
        for code, (name, module) in REQUIRED.items():
            perm = session.scalar(select(Permission).where(Permission.code == code))
            if not perm:
                perm = Permission(code=code, name=name, module=module)
                session.add(perm)
                session.flush()
            permissions.append(perm)
        existing = {p.code: p for p in role.permissions}
        role.permissions = list({**existing, **{p.code:p for p in permissions}}.values())
        user = session.scalar(select(User).where(User.email == email))
        if user:
            raise SystemExit("Usuário de homologação já existe; operação não altera senhas existentes.")
        user = User(
            email=email, full_name="Administrador — homologação rural",
            password_hash=hash_password(password), is_active=True, roles=[role],
        )
        session.add(user)
        session.commit()
    print("ADMIN_RURAL_HOMOLOG_CRIADO: banco isolado; e-mail não exibido.")


if __name__ == "__main__":
    main()
