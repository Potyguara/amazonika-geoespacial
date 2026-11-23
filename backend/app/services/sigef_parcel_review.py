"""Pré-validação de lote/parcelamento SIGEF e diagnóstico de sobreposição.

Sem certificação, sem inferência de titularidade e SEM alteração automática das
coordenadas ajustadas. Proximidade a divisa certificada exige avaliação técnica.
"""
from __future__ import annotations

import math
from typing import Any
from shapely.geometry import shape
from shapely.ops import nearest_points
from shapely.validation import explain_validity
from pyproj import Geod

from app.services.normative_checks import check_vertices
from app.services.sgl_metrics import sgl_metrics

GEOD = Geod(ellps="GRS80")
AREA_SITUATIONS = {"Imóvel Registrado", "Área Titulada não Registrada", "Área não Titulada"}
MAX_PARCELS = 50
MAX_VERTICES = 5000
MAX_NEIGHBORS = 200


def _polygon(value: dict, label: str):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: geometria GeoJSON obrigatória.")
    try:
        geometry = shape(value)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError(f"{label}: GeoJSON inválido.") from exc
    if geometry.geom_type != "Polygon":
        raise ValueError(f"{label}: somente Polygon é aceito nesta etapa.")
    if len(geometry.exterior.coords) > MAX_VERTICES + 1:
        raise ValueError(f"{label}: mais de {MAX_VERTICES} vértices.")
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError(f"{label}: perímetro inválido ({explain_validity(geometry)}).")
    west, south, east, north = geometry.bounds
    if not (-75 <= west < east <= -30 and -35 <= south < north <= 7):
        raise ValueError(f"{label}: coordenadas fora da abrangência brasileira.")
    return geometry


def _geo_area(geometry) -> float:
    return abs(GEOD.geometry_area_perimeter(geometry)[0]) / 10000.0


def _candidate_nearest_vertices(polygon, neighbor, max_count: int = 6) -> list[dict]:
    """Informação de apoio, não atualização de coordenadas."""
    proposed = []
    ring = list(polygon.exterior.coords)[:-1]
    for index, original in enumerate(ring):
        from shapely.geometry import Point
        old = Point(original)
        target = nearest_points(old, neighbor.boundary)[1]
        lon2, lat2 = float(target.x), float(target.y)
        azimuth, _, distance = GEOD.inv(old.x, old.y, lon2, lat2)
        if distance > 0.000001:
            proposed.append({
                "vertex_index": index + 1,
                "original_lon": round(old.x, 10),
                "original_lat": round(old.y, 10),
                "reference_lon": round(lon2, 10),
                "reference_lat": round(lat2, 10),
                "displacement_m": round(distance, 3),
                "azimuth_deg": round(azimuth % 360.0, 3),
                "purpose": "REFERENCIA_PARA_CONFERENCIA_EM_CAMPO",
            })
    proposed.sort(key=lambda item: item["displacement_m"])
    return proposed[:max_count]


def review_sigef_parcels(payload: dict[str, Any]) -> dict:
    """Validação preliminar, mantendo os valores cadastrais originais."""
    errors: list[str] = []
    warnings: list[str] = []
    identity = payload.get("identification") or {}
    parcels = payload.get("parcels") or []
    neighbors = payload.get("neighbors") or []
    municipalities = identity.get("municipalities") or []

    if not isinstance(identity, dict):
        raise ValueError("Identificação inválida.")
    if not isinstance(parcels, list) or not 1 <= len(parcels) <= MAX_PARCELS:
        raise ValueError("Informe de 1 a 50 parcelas.")
    if not isinstance(neighbors, list) or len(neighbors) > MAX_NEIGHBORS:
        raise ValueError("Máximo de 200 confrontantes vetoriais por revisão.")
    if not isinstance(municipalities, list) or len(municipalities) > 100:
        raise ValueError("Municípios inválidos ou em quantidade excessiva.")
    municipalities = [str(item).strip() for item in municipalities if str(item).strip()]
    if len(set(municipalities)) != len(municipalities):
        errors.append("Municípios duplicados na identificação.")
    if not municipalities:
        errors.append("Informe ao menos um município do imóvel.")
    if not str(identity.get("holder_name") or "").strip():
        errors.append("Informe nome ou razão social do titular.")
    document = "".join(ch for ch in str(identity.get("holder_document") or "") if ch.isdigit())
    if len(document) not in (11, 14):
        errors.append("CPF/CNPJ deve possuir 11 ou 14 dígitos.")
    situation = str(identity.get("situation") or "")
    if situation not in AREA_SITUATIONS:
        errors.append("Situação do imóvel não informada ou incompatível.")
    if not str(identity.get("property_name") or "").strip():
        errors.append("Denominação do imóvel obrigatória.")
    if situation == "Imóvel Registrado":
        if not str(identity.get("registration") or "").strip():
            errors.append("Imóvel registrado exige matrícula/transcrição confirmada.")
        if not str(identity.get("cns") or "").strip():
            errors.append("Imóvel registrado exige CNS do cartório.")

    parsed = []
    numbers = []
    vertex_checks: dict[str, tuple] = {}
    for index, item in enumerate(parcels, 1):
        if not isinstance(item, dict):
            errors.append(f"Parcela {index}: registro inválido.")
            continue
        name = str(item.get("name") or "").strip()
        number = str(item.get("number") or index).strip()
        if not name:
            errors.append(f"Parcela {index}: denominação obrigatória.")
        numbers.append(number)
        polygon = _polygon(item.get("geometry"), f"Parcela {index}")
        holes = len(polygon.interiors)
        if holes and not item.get("internal_perimeters_confirmed"):
            errors.append(
                f"Parcela {index}: {holes} vazio(s) interno(s); informar perímetros "
                "internos associados ao mesmo número de parcela."
            )
        if item.get("parcelling_type") not in (None, "", "SEM_PARCELAMENTO", "PARCELAMENTO", "ENCRAVADA"):
            errors.append(f"Parcela {index}: tipo de parcelamento desconhecido.")
        vertices = item.get("vertices")
        checks = None
        sgl_area = None
        if isinstance(vertices, list) and vertices:
            vertex_errors, checks, vertex_alerts = check_vertices(vertices, f"Parcela {number}")
            errors.extend(vertex_errors)
            warnings.extend(vertex_alerts)
            heights = [v.get("ellipsoidal_height_m") for v in vertices if isinstance(v, dict)]
            ring = [(v.get("longitude"), v.get("latitude")) for v in vertices if isinstance(v, dict)]
            try:
                sgl_area = round(sgl_metrics(ring, heights)["area_ha"], 4)
            except (ValueError, TypeError):
                warnings.append(f"Parcela {number}: área em SGL (MTGIR 3.8.3) não calculada; faltam alturas h.")
        parsed.append((number, name, polygon, holes))
        vertex_checks[number] = (checks, sgl_area)
    if len(set(numbers)) != len(numbers):
        errors.append("Números de parcelas duplicados.")
    internal_conflicts = []
    for i, (num_a, _, a, _) in enumerate(parsed):
        for num_b, _, b, _ in parsed[i+1:]:
            intersection = a.intersection(b)
            overlap = _geo_area(intersection) if not intersection.is_empty else 0.0
            if overlap > 0.0000001:
                internal_conflicts.append({"parcel_a": num_a, "parcel_b": num_b,
                                           "overlap_ha": round(overlap, 6)})
                errors.append(
                    f"Parcelas {num_a} e {num_b} se sobrepõem em {overlap:.6f} ha."
                )
    neighbor_conflicts = []
    for index, neighbor in enumerate(neighbors, 1):
        if not isinstance(neighbor, dict):
            raise ValueError(f"Confrontante {index}: registro inválido.")
        reference = _polygon(neighbor.get("geometry"), f"Confrontante {index}")
        ref_id = str(neighbor.get("reference_id") or index)
        provenance = str(neighbor.get("provenance") or "NAO_VERIFICADA")
        for parcel_num, _, polygon, _ in parsed:
            intersection = polygon.intersection(reference)
            overlap = _geo_area(intersection) if not intersection.is_empty else 0.0
            if overlap <= 0.0000001:
                continue
            proposals = _candidate_nearest_vertices(polygon, reference)
            neighbor_conflicts.append({
                "parcel_number": parcel_num,
                "neighbor_reference": ref_id,
                "provenance": provenance,
                "overlap_ha": round(overlap, 6),
                "reference_displacements": proposals,
                "change_applied": False,
                "requires_resurvey_and_technical_approval": True,
            })
            errors.append(
                f"Parcela {parcel_num} intersecta confrontante {ref_id} "
                f"({overlap:.6f} ha); verificar limites e documentação."
            )
            if provenance != "SIGEF_CERTIFICADA_VERIFICADA":
                warnings.append(
                    f"Confrontante {ref_id}: certificação não foi comprovada; "
                    "a geometria é apenas referência preliminar."
                )
    if not neighbors:
        warnings.append(
            "Nenhuma base vizinha foi fornecida: não é possível afirmar ausência de sobreposição."
        )
    warnings.append(
        "A verificação oficial no SIGEF consulta também parcelas e vértices já certificados; "
        "este teste local não substitui a validação ou a certificação pelo INCRA."
    )
    return {
        "status": "BLOCKED" if errors else "PREVALIDATED",
        "eligible_for_official_submission": False,
        "errors": errors,
        "warnings": warnings,
        "municipalities": municipalities,
        "parcel_count": len(parsed),
        "parcels": [{"number": n, "name": name,
                     "area_ha": vertex_checks.get(n, (None, None))[1] or round(_geo_area(poly), 4),
                     "area_method": "SGL_GRS80_MTGIR_3_8_3" if vertex_checks.get(n, (None, None))[1] else "GEODESIC_PRELIMINARY",
                     "vertex_checks": vertex_checks.get(n, (None, None))[0],
                     "internal_perimeter_count": holes}
                    for n, name, poly, holes in parsed],
        "internal_overlaps": internal_conflicts,
        "neighbor_overlaps": neighbor_conflicts,
        "original_geometries_preserved": True,
        "coordinates_modified": False,
    }
