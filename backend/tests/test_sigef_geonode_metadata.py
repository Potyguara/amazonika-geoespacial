"""Regression checks for GeoNode catalogue timestamps and their semantics."""
from app.services.sigef_geonode_metadata import parse_sigef_catalogue_metadata


def test_reads_catalogue_last_updated_without_mislabeling_as_feature_update():
    item = {
        "dataset": {
            "title": "Sigef - todas parcelas",
            "alternate": "geonode:sigef_geo",
            "last_updated": "2026-11-04T01:24:00Z",
            "date": "2026-07-27T15:05:00Z",
        }
    }
    result = parse_sigef_catalogue_metadata(item)
    assert result["last_modified"] == "2026-11-04T01:24:00Z"
    assert result["timestamp_field"] == "last_updated"
    assert result["meaning"] == "modificacao_registro_catalogo"


def test_refuses_to_use_publication_or_individual_parcel_dates():
    result = parse_sigef_catalogue_metadata({
        "title": "Sigef - todas parcelas",
        "date": "2026-07-27T15:05:00Z",
        "data_aprovacao": "2014-08-04T11:21:09Z",
    })
    assert result["available"] is False
    assert result["last_modified"] is None


def test_refuses_unrelated_dataset():
    result = parse_sigef_catalogue_metadata({
        "title": "Outro dataset",
        "alternate": "geonode:other",
        "last_updated": "2026-11-04T01:24:00Z",
    })
    assert result["available"] is False
