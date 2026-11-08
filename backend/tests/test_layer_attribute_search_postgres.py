"""Real PostGIS attribute-search integration using the disposable test database.

Opt-in only. Hard-coded isolated host/db/user guard; no remote WFS,
no modifications to production or rural homologation databases.
"""
import os
from uuid import uuid4

import pytest
from shapely.geometry import Polygon
from geoalchemy2.shape import from_shape
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("AMAZONIKA_TEST_CONSOLIDATED_PG") != "yes",
    reason="Requires disposable consolidated-postgres database",
)


def test_searches_anm_process_like_attribute_and_returns_polygon():
    import app.models
    from app.db.base import Base
    from app.db.session import engine
    from app.models.catalog import Source, SourceKind, SourceVersion, GeoFeature
    from app.api.routes.layer_search import layer_fields, search_features

    if not (
        engine.url.host == "consolidated-postgres"
        and engine.url.database == "amazonika_consolidated_test"
        and engine.url.username == "consolidated"
    ):
        pytest.fail("Blocked: wrong PostGIS database")

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)

    source_id = uuid4()
    version_id = uuid4()
    geom = Polygon([
        (-51.12, .02), (-51.11, .02), (-51.11, .03),
        (-51.12, .03), (-51.12, .02),
    ])
    with Session(engine) as db:
        db.add(Source(
            id=source_id, slug="search-test-" + source_id.hex[:12],
            name="Processos minerários — teste isolado",
            institution="ANM", kind=SourceKind.MANUAL,
            is_official=False, is_active=True,
            metadata_json={},
        ))
        db.flush()
        db.add(SourceVersion(
            id=version_id, source_id=source_id,
            status="READY", is_current=True, feature_count=1,
        ))
        db.flush()
        db.add(GeoFeature(
            version_id=version_id, external_id="850123/2020",
            name="Processo 850123/2020",
            properties={"PROCESSO": "850123/2020", "FASE": "Pesquisa"},
            geom=from_shape(geom, srid=4674),
        ))
        db.commit()

    with Session(engine) as db:
        metadata = layer_fields(source_id=source_id, db=db)
        assert "PROCESSO" in metadata["fields"]
        output = search_features(
            source_id=source_id, q="850123",
            field="PROCESSO", limit=10, db=db,
        )
        assert len(output["results"]) == 1
        found = output["results"][0]
        assert found["matched_value"] == "850123/2020"
        assert found["geometry"]["type"] == "Polygon"
        assert found["bbox"][0] == pytest.approx(-51.12)
        assert found["bbox"][2] == pytest.approx(-51.11)
        missing = search_features(
            source_id=source_id, q="999999",
            field="PROCESSO", limit=10, db=db,
        )
        assert missing["results"] == []

    # All data lives only in the disposable database and is removed with it.
