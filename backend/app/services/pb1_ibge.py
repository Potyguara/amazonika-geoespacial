"""Read the declared IBGE hgeoHNOR2020 ID LAT LON ETA SIGMA GRADE output."""
from math import isfinite


def parse_ibge_output(raw: str, points: list[dict]) -> dict[str, list[float]]:
    known = {p["name"]: p for p in points}
    result = {}
    for number, line in enumerate(raw.lstrip("\ufeff").splitlines(), 1):
        if not line.strip():
            continue
        cells = line.split()
        if len(cells) != 6:
            raise ValueError(f"Linha {number}: esperado ID LAT LON ETA SIGMA GRADE.")
        name, lat, lon, eta, sigma, grade = cells
        if name not in known or name in result:
            raise ValueError(f"Identificador desconhecido ou duplicado: {name}")
        try:
            lat, lon, eta, sigma = map(float, (lat, lon, eta, sigma))
        except ValueError as exc:
            raise ValueError(f"Valor numérico inválido: {name}") from exc
        if not all(map(isfinite, (lat, lon, eta, sigma))) or sigma < 0:
            raise ValueError(f"Fator ou incerteza inválida: {name}")
        p = known[name]
        if abs(lat - p["latitude"]) > 0.000001 or abs(lon - p["longitude"]) > 0.000001:
            raise ValueError(f"Coordenadas divergentes: {name}")
        if not any(v in grade.upper() for v in ("HGEOHNOR", "SANTANA", "IMBITUBA")):
            raise ValueError(f"Grade não reconhecida: {grade}")
        result[name] = [eta, sigma]
    if set(result) != set(known) or not result:
        raise ValueError("O arquivo deve conter exatamente todos os V PB1 salvos.")
    return result
