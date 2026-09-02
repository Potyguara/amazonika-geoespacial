from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.auth import Permission, Role


PERMISSIONS = [
    ("sources.view", "Visualizar fontes de dados", "sources"),
    ("sources.manage", "Gerenciar fontes de dados", "sources"),
    ("sources.import", "Importar bases geoespaciais", "sources"),
    ("analysis.view", "Visualizar análises", "analysis"),
    ("analysis.execute", "Executar análises espaciais", "analysis"),
    ("analysis.export", "Exportar resultados e relatórios", "analysis"),
    ("projects.view", "Visualizar projetos", "projects"),
    ("projects.create", "Criar projetos", "projects"),
    ("projects.edit", "Editar projetos", "projects"),
    ("projects.delete", "Excluir projetos", "projects"),
    ("users.view", "Visualizar usuários", "users"),
    ("users.manage", "Gerenciar usuários", "users"),
    ("audit.view", "Visualizar auditoria", "audit"),
]

ROLE_PERMISSIONS = {
    "ADMINISTRADOR": "*",
    "ANALISTA": [
        "sources.view",
        "analysis.view",
        "analysis.execute",
        "analysis.export",
        "projects.view",
        "projects.create",
        "projects.edit",
    ],
}

ROLE_NAMES = {
    "ADMINISTRADOR": "Administrador",
    "ANALISTA": "Analista",
}


def main():
    db = SessionLocal()

    try:
        permissions = {}

        for code, name, module in PERMISSIONS:
            permission = db.scalar(
                select(Permission).where(Permission.code == code)
            )

            if not permission:
                permission = Permission(
                    code=code,
                    name=name,
                    module=module,
                )
                db.add(permission)
                db.flush()
            else:
                permission.name = name
                permission.module = module

            permissions[code] = permission

        for code, role_name in ROLE_NAMES.items():
            role = db.scalar(
                select(Role).where(Role.code == code)
            )

            if not role:
                role = Role(code=code, name=role_name)
                db.add(role)
                db.flush()
            else:
                role.name = role_name

            configured = ROLE_PERMISSIONS[code]

            if configured == "*":
                role.permissions = list(permissions.values())
            else:
                role.permissions = [
                    permissions[permission_code]
                    for permission_code in configured
                ]

        db.commit()
        print("AUTH_BOOTSTRAP_OK")

    finally:
        db.close()


if __name__ == "__main__":
    main()
