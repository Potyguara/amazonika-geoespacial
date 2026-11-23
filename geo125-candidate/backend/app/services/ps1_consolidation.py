"""Consolidação PS1: resultados calculados, nunca sigmas arbitrários."""
from app.services.ps1_accuracy import evaluate_ps1_checkpoints, ps1_height, _number
from app.services.topcon_perimeter_review import review_topcon_perimeter


def consolidate_ps1(boundary, start, vertices, checkpoints, category, kind, sample_height):
    if not 1 <= len(vertices) <= 4997 or len(boundary) + len(vertices) > 5000:
        raise ValueError("Quantidade de vértices inválida.")
    if any(p.get("sigef_method") == "PS1" for p in boundary):
        raise ValueError("Revise o trecho PS1 existente antes de reconstruí-lo.")
    matches = [i for i, p in enumerate(boundary) if p.get("sigef_vertex_code") == start]
    if len(matches) != 1:
        raise ValueError("Selecione o vértice inicial do trecho.")
    if len({str(p.get("parcel_number")) for p in boundary}) != 1:
        raise ValueError("Selecione apenas uma parcela.")
    i = matches[0]
    initial = boundary[i]
    accuracy = evaluate_ps1_checkpoints(checkpoints, category)
    if not accuracy["within_horizontal_limit"] or min(accuracy[k] for k in ("sigma_e_m", "sigma_n_m", "sigma_h_m")) <= 0:
        raise ValueError("Acurácia PS1 incompatível ou sem precisão positiva documentada.")
    generated = []
    for item in vertices:
        code = str(item.get("code") or "").strip().upper()
        if "-V-" not in code:
            raise ValueError("Informe código SIGEF de vértice virtual.")
        lon, lat = _number(item.get("longitude")), _number(item.get("latitude"))
        if not (-75 <= lon <= -30 and -35 <= lat <= 7):
            raise ValueError("Coordenada fora da abrangência brasileira.")
        source = sample_height(lon, lat)
        h = ps1_height(source, accuracy["sigma_h_m"], kind=kind,
                       factor=item.get("factor"), factor_sigma=item.get("factor_sigma"))
        generated.append({
            "name": code, "sigef_vertex_code": code, "point_role": "BOUNDARY",
            "parcel_number": initial.get("parcel_number"), "parcel_name": initial.get("parcel_name"),
            "longitude": lon, "latitude": lat, "sigef_method": "PS1",
            "boundary_type": initial.get("boundary_type"), "boundary_detail": initial.get("boundary_detail"),
            "confrontant": initial.get("confrontant"), "confrontant_cns": initial.get("confrontant_cns"),
            "confrontant_registration": initial.get("confrontant_registration"),
            "ellipsoidal_height_m": h["ellipsoidal_height_m"],
            "height_reference_confirmed": False, "sigma_reference_confirmed": False,
            "sigma_lon_m": accuracy["sigma_e_m"], "sigma_lat_m": accuracy["sigma_n_m"],
            "sigma_h_m": h["sigma_h_m"], "sigma_hz_m": accuracy["horizontal_rms_m"],
            "derived_physical_altitude_m": h.get("normal_height_m"),
            "derived_physical_model": "HN" if "normal_height_m" in h else None,
            "derived_calculation": {"method": "PS1", "status": "REVIEW_REQUIRED",
                                    "accuracy_verified": False, "source_elevation_m": source,
                                    "accuracy": accuracy},
        })
    merged = [*boundary[:i+1], *generated, *boundary[i+1:]]
    review = review_topcon_perimeter(merged)
    if not review["ready_for_geometry"]:
        raise ValueError("; ".join(review["errors"]))
    if any("repetidos" in e or "horário" in e for e in review["ods_errors"]):
        raise ValueError("; ".join(review["ods_errors"]))
    return {"vertices": merged, "generated": generated, "accuracy": accuracy,
            "geometry": review["geometry"], "ready_for_sigef": False}
