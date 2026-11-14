"""GEO-81E: teste HTTP autenticado contra API + PostGIS TEMPORÁRIOS.

Este módulo se recusa a rodar em qualquer banco que não seja o container
geo81_test especificado, não recebe credenciais de produção e não grava ODS.
Executar com a API candidata e banco na rede Docker interna de homologação.
"""
from __future__ import annotations

import io
import json
import os
import secrets
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy.engine import make_url

BASE = os.environ.get("GEO81_API_URL", "http://amazonika-geo81-api:8000").rstrip("/")
url = make_url(os.environ.get("DATABASE_URL", ""))
if (
    url.host != "amazonika-geo81-db"
    or url.database != "geo81_test"
    or url.username != "geo81"
    or BASE != "http://amazonika-geo81-api:8000"
):
    raise SystemExit(
        "BLOQUEADO: ambiente de homologação esperado não identificado. "
        "Não execute contra produção."
    )

from app.db.session import SessionLocal
from app.models.auth import Permission, Role, User
from app.core.security import hash_password
from app.services.technical_import import parse_sigef_ods


def http_post(path: str, body: bytes, content_type: str, cookie: str = ""):
    headers = {"Content-Type": content_type}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def json_post(path: str, payload: dict, cookie: str = ""):
    status, headers, body = http_post(
        path, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        "application/json; charset=utf-8", cookie,
    )
    try:
        parsed = json.loads(body)
    except ValueError:
        raise AssertionError(f"{path}: resposta não JSON: status={status}")
    return status, headers, parsed


def vertex(name: str, lon: float, lat: float) -> dict:
    return {
        "name": name, "point_role": "BOUNDARY", "sigef_vertex_code": name,
        "longitude": lon, "latitude": lat,
        "ellipsoidal_height_m": -2.1, "height_reference_confirmed": True,
        "sigma_hz_m": 0.018,
        "sigma_lon_m": 0.01, "sigma_lat_m": 0.01, "sigma_h_m": 0.025,
        "sigef_method": "PG1", "boundary_type": "LA6",
        "confrontant": "CONFRONTANTE DE TESTE",
        "confrontant_cns": "", "confrontant_registration": "",
    }


def check(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main():
    # Usuário, senha e permissões só existem no banco descartável geo81_test.
    email = f"geo81-{secrets.token_hex(8)}@example.invalid"
    password = secrets.token_urlsafe(32)
    with SessionLocal() as session:
        permission = Permission(
            code="analysis.execute", name="Executar análise",
            module="analysis",
        )
        role = Role(code="ADMINISTRADOR", name="Admin homologação")
        role.permissions.append(permission)
        user = User(
            email=email, full_name="Responsável de teste GEO81",
            password_hash=hash_password(password),
            is_active=True,
        )
        user.roles.append(role)
        session.add(user)
        session.commit()

    route = "/api/v1/technical-pieces"
    code, _, result = json_post(route + "/sigef/parcels-review", {})
    check(code == 401, f"sem autenticação: esperado 401, recebido {code}")
    print("1/7 Proteção sem autenticação: HTTP 401")

    code, headers, result = json_post(
        "/api/v1/auth/login", {"email": email, "password": password}
    )
    check(code == 200, f"login: HTTP {code}, resposta {result}")
    session_cookie = SimpleCookie()
    session_cookie.load(headers.get("Set-Cookie", ""))
    check("amazonika_session" in session_cookie, "cookie de sessão ausente")
    cookie = "amazonika_session=" + session_cookie["amazonika_session"].value
    print("2/7 Login real e cookie de sessão: HTTP 200")

    vertices_a = [
        vertex("TEST-M-0001", -51.4, 0.4),
        vertex("TEST-M-0002", -51.39, 0.39),
        vertex("TEST-M-0003", -51.41, 0.39),
    ]
    vertices_b = [
        vertex("TEST-M-0004", -51.38, 0.4),
        vertex("TEST-M-0005", -51.37, 0.39),
        vertex("TEST-M-0006", -51.39, 0.39),
    ]
    boundary = route + "/topcon/perimeter-review"
    code, _, review = json_post(boundary, {"points": vertices_a}, cookie)
    check(code == 200 and review.get("ready_for_ods") is True,
          f"revisão Topcon: HTTP {code} {review}")
    print("3/7 Revisão dos vértices: HTTP 200")

    code, _, vertical = json_post(route + "/topcon/vertical-conversion", {
        "model": "hgeoHNOR2020",
        "points": [{
            "name": "TEST-M-0001",
            "latitude": 0.4, "longitude": -51.4,
            "ellipsoidal_height_m": -2.1, "conversion_factor_m": 10.2,
            "factor_origin": "FATOR FICTÍCIO - SOMENTE TESTE",
            "height_reference_confirmed": True,
        }],
    }, cookie)
    check(code == 200 and vertical.get("status") == "READY",
          f"altimetria: HTTP {code} {vertical}")
    check(abs(vertical["points"][0]["normal_height_m"] + 12.3) < 1e-6,
          "Altitude normal incorreta")
    check(vertical["points"][0]["sigef_h_m"] == -2.1,
          "h SIGEF foi substituída indevidamente")
    print("4/7 Conversão altimétrica: h preservada, HN calculada")

    identity = {
        "holder_name": "TITULAR FICTÍCIO GEO81",
        "holder_document": "12345678901",
        "property_name": "IMÓVEL DE TESTE GEO81",
        "situation": "Área não Titulada",
        "municipalities": ["Macapá-AP", "Santana-AP"],
    }
    parcels = [
        {"number": "1", "name": "PARCELA DE TESTE A", "vertices": vertices_a},
        {"number": "2", "name": "PARCELA DE TESTE B", "vertices": vertices_b},
    ]
    check_geo = [review["geometry"], None]
    code, _, verified = json_post(route + "/sigef/parcels-review", {
        "identification": identity,
        "parcels": [
            {"number": p["number"], "name": p["name"],
             "geometry": check_geo[i] if i == 0 else {
                 "type": "Polygon",
                 "coordinates": [[
                     [-51.38, 0.4], [-51.37, 0.39],
                     [-51.39, 0.39], [-51.38, 0.4],
                 ]],
             }}
            for i, p in enumerate(parcels)
        ],
        "neighbors": [],
    }, cookie)
    check(code == 200 and verified.get("status") == "PREVALIDATED",
          f"pré-validação parcelas: HTTP {code} {verified}")
    check(verified.get("parcel_count") == 2, "Número de parcelas incorreto")
    print("5/7 Revisão de duas parcelas e municípios: HTTP 200")

    ods_path = route + "/sigef/reviewed-ods"
    code, headers, raw = http_post(
        ods_path,
        json.dumps({"identification": identity, "parcels": parcels, "neighbors": []},
                   ensure_ascii=False).encode(),
        "application/json", cookie,
    )
    check(code == 200, f"exportação ODS: HTTP {code} {raw[:500]!r}")
    check(raw[:2] == b"PK", "download não é ODS/ZIP")
    check(headers.get("X-Sigef-Validation") == "PREVALIDACAO_LOCAL",
          "ODS indevidamente rotulada como certificada")
    parsed = parse_sigef_ods(raw)
    check(parsed["vertex_count"] == 6, "ODS tem contagem incorreta de vértices")
    check(len(parsed["features"]) == 2, "ODS não tem duas parcelas")
    print(f"6/7 ODS gerada: {len(raw)} bytes, duas parcelas, seis vértices")

    boundary = "geo81" + secrets.token_hex(8)
    multipart = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="geo81.ods"\r\n'
        "Content-Type: application/vnd.oasis.opendocument.spreadsheet\r\n\r\n"
    ).encode() + raw + f"\r\n--{boundary}--\r\n".encode()
    code, _, imported = json_post_raw_multipart(
        route + "/import-sigef-ods", multipart, boundary, cookie
    )
    check(code == 200, f"reimportação: HTTP {code} {str(imported)[:500]}")
    check(imported.get("vertex_count") == 6 and len(imported.get("features", [])) == 2,
          "Reimportação alterou geometria/vértices")
    print("7/7 Reimportação HTTP: duas parcelas e seis vértices preservados")
    print("GEO-81E HTTP AUTENTICADO APROVADO — BANCO ISOLADO")


def json_post_raw_multipart(path, data, boundary, cookie):
    code, _, body = http_post(
        path, data, f"multipart/form-data; boundary={boundary}", cookie
    )
    try:
        result = json.loads(body)
    except ValueError:
        raise AssertionError(f"multipart: resposta inválida HTTP {code}")
    return code, {}, result


if __name__ == "__main__":
    main()
