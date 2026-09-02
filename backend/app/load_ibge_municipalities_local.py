from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import text

from app.db.session import engine


def _pick(props: dict, *names: str) -> str:
    lowered = {str(k).lower(): v for k, v in props.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value)
    return ""


def load_zip(zip_file: str, uf: str, year: int = 2025) -> None:
    uf = uf.strip().upper()
    zip_path = Path(zip_file).resolve()
    if not zip_path.exists():
        raise SystemExit(f"Arquivo não encontrado: {zip_path}")

    with tempfile.TemporaryDirectory(prefix="ibge-municipios-") as tmp:
        geojson_path = Path(tmp) / f"{uf}_Municipios_{year}.geojson"
        with ZipFile(zip_path) as z:
            shp_names = [name for name in z.namelist() if name.lower().endswith('.shp')]
            if not shp_names:
                raise SystemExit("ZIP não contém arquivo .shp")
            shp_name = shp_names[0]

        subprocess.run(
            [
                "ogr2ogr",
                "-f",
                "GeoJSON",
                str(geojson_path),
                f"/vsizip/{zip_path}/{shp_name}",
                "-t_srs",
                "EPSG:4674",
            ],
            check=True,
        )

        features = json.loads(geojson_path.read_text()).get("features") or []
        if not features:
            raise SystemExit("Malha municipal convertida sem feições")

        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ibge_municipios_2025 (
                    cd_mun VARCHAR(20) NOT NULL,
                    nm_mun VARCHAR(180) NOT NULL,
                    sigla_uf VARCHAR(2) NOT NULL,
                    ano_referencia INTEGER NOT NULL DEFAULT 2025,
                    geom geometry(MultiPolygon, 4674) NOT NULL,
                    PRIMARY KEY (cd_mun, ano_referencia)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ibge_municipios_2025_geom ON ibge_municipios_2025 USING gist (geom)"))
            conn.execute(
                text("DELETE FROM ibge_municipios_2025 WHERE sigla_uf=:uf AND ano_referencia=:year"),
                {"uf": uf, "year": year},
            )

            inserted = 0
            for feature in features:
                props = feature.get("properties") or {}
                geom = feature.get("geometry")
                cd_mun = _pick(props, "CD_MUN", "CD_GEOCMU", "GEOCODIGO")
                nm_mun = _pick(props, "NM_MUN", "NM_MUNICIP", "NOME")
                sigla_uf = _pick(props, "SIGLA_UF", "UF") or uf
                if not cd_mun or not nm_mun or not geom:
                    continue
                conn.execute(text("""
                    INSERT INTO ibge_municipios_2025
                        (cd_mun,nm_mun,sigla_uf,ano_referencia,geom)
                    VALUES
                        (:cd_mun,:nm_mun,:sigla_uf,:year,
                         ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom),4674)))
                    ON CONFLICT (cd_mun,ano_referencia)
                    DO UPDATE SET nm_mun=EXCLUDED.nm_mun,
                                  sigla_uf=EXCLUDED.sigla_uf,
                                  geom=EXCLUDED.geom
                """), {
                    "cd_mun": cd_mun,
                    "nm_mun": nm_mun,
                    "sigla_uf": sigla_uf,
                    "year": year,
                    "geom": json.dumps(geom),
                })
                inserted += 1

        print(f"OK - {inserted} municípios {uf} carregados na referência estrutural IBGE {year}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Uso: python -m app.load_ibge_municipalities_local /caminho/AP_Municipios_2025.zip AP [2025]")
    load_zip(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2025)
