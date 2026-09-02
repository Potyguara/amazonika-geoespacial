import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Source
from app.services.importer import synchronize_source_data


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m app.sync_source <slug-da-fonte>")

    slug = sys.argv[1]
    with SessionLocal() as db:
        source = db.scalar(select(Source).where(Source.slug == slug))
        if source is None:
            raise SystemExit(f"Fonte não encontrada: {slug}")
        if source.kind.value not in ("WFS","ARCGIS_FEATURE"):
            raise SystemExit(f"A fonte {slug} não permite sincronização automática")
        version = synchronize_source_data(db, source)
        print(f"Sincronização concluída: {source.name} — {version.feature_count} feições")


if __name__ == "__main__":
    main()
