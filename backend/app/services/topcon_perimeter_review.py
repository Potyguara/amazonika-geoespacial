"""Pré-validação de perímetro levantado via Topcon Tools.

Não transforma elevação em altura elipsoidal e não gera ODS certificável.
O responsável escolhe e ordena vértices; as confirmações cadastrais
são explícitas, sem completar informações faltantes.
"""
from __future__ import annotations

import math
from collections import Counter

from pyproj import Geod
from shapely.geometry import Polygon
from app.services.sgl_metrics import sgl_metrics

MAX_VERTICES = 5000
GEOD = Geod(ellps="GRS80")


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def review_topcon_perimeter(points: list[dict]) -> dict:
    """Retorna erros acionáveis e GeoJSON somente para perímetro consistente."""
    errors: list[str] = []
    warnings: list[str] = []
    ods_errors: list[str] = []
    if len(points) < 3:
        errors.append("Selecione ao menos três vértices de divisa.")
    if len(points) > MAX_VERTICES:
        errors.append("O perímetro excede 5.000 vértices.")
    names = [str(p.get("name") or "").strip() for p in points if isinstance(p, dict)]
    repeated = [name for name, count in Counter(names).items() if name and count > 1]
    if repeated:
        errors.append("Pontos Topcon repetidos: " + ", ".join(repeated[:10]))
    codes: list[str] = []
    coords: list[tuple[float, float]] = []
    safe_vertices: list[dict] = []
    missing_precisions: list[str] = []
    for index, point in enumerate(points, 1):
        if not isinstance(point, dict):
            errors.append(f"Linha {index}: registro inválido.")
            continue
        name = str(point.get("name") or "").strip()
        role = str(point.get("point_role") or "").strip().upper()
        code = str(point.get("sigef_vertex_code") or "").strip().upper()
        method = str(point.get("sigef_method") or "").strip()
        boundary = str(point.get("boundary_type") or "").strip()
        confrontant = str(point.get("confrontant") or "").strip()
        longitude = point.get("longitude")
        latitude = point.get("latitude")
        height = point.get("ellipsoidal_height_m")
        sigma_hz = point.get("sigma_hz_m")
        sigma_lon = point.get("sigma_lon_m")
        sigma_lat = point.get("sigma_lat_m")
        # Dados individuais confirmados pelo RT prevalecem sobre sigma
        # horizontal de referência, sem recorrer ao RMS dos vetores.
        if (_finite(sigma_lon) and _finite(sigma_lat)
                and sigma_lon >= 0 and sigma_lat >= 0):
            sigma_hz = math.hypot(sigma_lon, sigma_lat)
        if role == "CONTROL" or name.casefold() in ("base", "estacao base", "estação base"):
            errors.append(f"Linha {index}: ponto de controle {name or 'sem nome'} não pode integrar a divisa.")
        if not name:
            errors.append(f"Linha {index}: nome do ponto Topcon ausente.")
        if not code:
            ods_errors.append(f"Linha {index} ({name}): código oficial do vértice ausente.")
        elif len(code) > 60:
            errors.append(f"Linha {index}: código do vértice muito longo.")
        else:
            codes.append(code)
        if not method:
            ods_errors.append(f"Linha {index} ({name}): método de posicionamento pendente.")
        if not boundary:
            ods_errors.append(f"Linha {index} ({name}): tipo de limite pendente.")
        if not confrontant:
            ods_errors.append(f"Linha {index} ({name}): confrontante do segmento seguinte pendente.")
        if not _finite(height):
            ods_errors.append(f"Linha {index} ({name}): altura elipsoidal h pendente.")
        if not (_finite(sigma_lon) and _finite(sigma_lat)
                and _finite(point.get("sigma_h_m"))
                and sigma_lon > 0 and sigma_lat > 0 and point["sigma_h_m"] > 0):
            missing_precisions.append(code or name)
        # A falta de precisões por eixo é pendência exclusiva da exportação ODS;
        # não invalida a geometria topológica ou a peça preliminar.
        if not _finite(sigma_hz) or sigma_hz < 0:
            warnings.append(f"Linha {index} ({name}): precisão horizontal não informada.")
        if not (_finite(longitude) and _finite(latitude) and -75 <= longitude <= -30 and -35 <= latitude <= 7):
            errors.append(f"Linha {index} ({name}): coordenada fora da abrangência brasileira.")
            continue
        coords.append((float(longitude), float(latitude)))
        safe_vertices.append({
            "name": name, "sigef_vertex_code": code, "sigef_method": method,
            "boundary_type": boundary, "confrontant": confrontant,
            "longitude": float(longitude), "latitude": float(latitude),
            "ellipsoidal_height_m": height if _finite(height) else None,
            "sigma_hz_m": sigma_hz if _finite(sigma_hz) else None,
        })
    if len(set(codes)) != len(codes):
        ods_errors.append("Existem códigos SIGEF repetidos no perímetro.")
    if len(set(coords)) != len(coords):
        errors.append("Existem coordenadas repetidas no perímetro.")
    geometry = None
    area_ha = None
    perimeter_m = None
    metrics_method = None
    if len(coords) >= 3 and len(set(coords)) >= 3:
        polygon = Polygon(coords)
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            errors.append("O perímetro é inválido (cruzamento, repetição ou área nula).")
        else:
            signed_area, perimeter_m = GEOD.polygon_area_perimeter(
                [p[0] for p in coords], [p[1] for p in coords]
            )
            area_ha = abs(signed_area) / 10000.0
            metrics_method = "GEODESIC_PRELIMINARY"
            heights = [v["ellipsoidal_height_m"] for v in safe_vertices]
            if all(_finite(h) for h in heights):
                metrics = sgl_metrics(coords, heights)
                area_ha = metrics["area_ha"]
                perimeter_m = metrics["perimeter_m"]
                metrics_method = "SGL_GRS80"
                if not all(p.get("height_reference_confirmed") is True for p in points):
                    warnings.append("SGL calculado com alturas disponíveis, ainda sujeitas à confirmação do referencial.")
            else:
                warnings.append("Área e perímetro geodésicos preliminares: faltam alturas h para SGL.")
            if signed_area >= 0:
                ods_errors.append("Ordene os vértices em sentido horário antes de exportar.")
            northernmost = max(range(len(coords)), key=lambda i: (coords[i][1], -coords[i][0]))
            if northernmost != 0:
                ods_errors.append(
                    f"O primeiro vértice deve ser o mais ao norte: posição {northernmost + 1}."
                )
            geometry = {"type": "Polygon", "coordinates": [[list(p) for p in coords + [coords[0]]]]}
    if not points:
        warnings.append("Nenhum ponto selecionado; a estação base deve permanecer fora do perímetro.")
    if any(str(p.get("point_role") or "") == "UNCLASSIFIED" for p in points if isinstance(p, dict)):
        warnings.append("Existem pontos originalmente não classificados; confirme seu vínculo à divisa.")
    if ods_errors:
        warnings.append("ODS ainda incompleta: " + "; ".join(ods_errors[:5]))
    if missing_precisions:
        warnings.append("ODS: precisões individuais por eixo pendentes para " +
                        ", ".join(missing_precisions[:20]) + ".")
    return {
        "ready_for_geometry": not errors,
        "ready_for_ods": not errors and not ods_errors and not missing_precisions,
        "missing_sigmas": missing_precisions,
        "ods_errors": ods_errors,
        "errors": errors, "warnings": warnings,
        "vertex_count": len(points), "vertices": safe_vertices,
        "geometry": geometry if not errors else None,
        "metrics_method": metrics_method,
        "area_ha": round(area_ha, 4) if area_ha is not None else None,
        "perimeter_m": round(perimeter_m, 3) if perimeter_m is not None else None,
        "disclaimer": "Pré-validação local: não é certificação do SIGEF/INCRA.",
    }
