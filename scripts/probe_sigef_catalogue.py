"""Show only the official SIGEF catalogue modification information.

Run from VPS: python3 scripts/probe_sigef_catalogue.py
"""
import json
from urllib.request import Request, urlopen

URL = "https://geonodeincra.serpro.gov.br/api/v2/datasets/1/"


def main():
    req = Request(URL, headers={"Accept": "application/json", "User-Agent": "Amazonika-Geoespacial/1.0"})
    with urlopen(req, timeout=20) as response:
        raw = response.read(512_001)
        print("HTTP:", response.status, "| Content-Type:", response.headers.get("Content-Type"))
    if len(raw) > 512_000:
        raise ValueError("Resposta excedeu 512 KB")
    payload = json.loads(raw)
    for name, data in (
        ("root", payload),
        ("dataset", payload.get("dataset") if isinstance(payload, dict) else None),
        ("resource", payload.get("resource") if isinstance(payload, dict) else None),
    ):
        if not isinstance(data, dict):
            continue
        print(name, "keys:", ", ".join(sorted(data.keys())[:70]))
        for field in ("title", "alternate", "name", "last_updated", "last_modified", "modified", "date_modified", "date", "created"):
            if field in data:
                print(name + "." + field + ":", str(data[field])[:120])


if __name__ == "__main__":
    main()
