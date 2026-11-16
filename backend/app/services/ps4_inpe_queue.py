"""Fila persistente de preparação de recortes PS4.

Um único worker processa jobs serialmente; todos os caminhos são derivados de
UUIDs autenticados. O job guarda apenas IDs/coleção/BBOX, nunca URLs arbitrárias.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from tempfile import NamedTemporaryFile

from app.core.config import get_settings
from app.services.inpe_ps4_import import COLLECTIONS, validate_crop

TERMINAL = frozenset(("READY", "FAILED", "CANCELLED"))
ACTIVE = frozenset(("QUEUED", "PROCESSING"))
MAX_BYTES = 12_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jobs_root() -> Path:
    root = get_settings().storage_dir / ".ps4_inpe_jobs"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def job_file(job_id: UUID) -> Path:
    return jobs_root() / f"{job_id}.json"


def save_job(job: dict) -> None:
    path = job_file(UUID(str(job["id"])))
    encoded = json.dumps(job, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_BYTES:
        raise ValueError("Metadados do job acima do tamanho permitido.")
    with NamedTemporaryFile(dir=path.parent, prefix=".ps4-", delete=False) as tmp:
        temporary = Path(tmp.name)
        try:
            os.fchmod(tmp.fileno(), 0o600)
            tmp.write(encoded)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def read_job(job_id: UUID) -> dict:
    path = job_file(job_id)
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError("Job PS4 inválido.")
    return json.loads(data)


def new_job(user_id: UUID, piece_id: UUID, item_id: str,
            collection: str, bbox: tuple[float, float, float, float]) -> dict:
    if collection not in COLLECTIONS:
        raise ValueError("Coleção CBERS-4A não permitida.")
    validate_crop(bbox)
    # Validação do ID sem rede: a obtenção do item será feita pelo worker.
    # Reutilizar a validação estrita do catálogo para evitar livre-form no job.
    from app.services.inpe_ps4_import import _ITEM_ID, _L4_ITEM_ID, L4_COLLECTION
    regex = _L4_ITEM_ID if collection == L4_COLLECTION else _ITEM_ID
    if not regex.fullmatch(item_id):
        raise ValueError("Identificador STAC inválido para coleção.")
    return {
        "id": str(uuid4()), "piece_id": str(piece_id), "user_id": str(user_id),
        "item_id": item_id, "collection": collection, "bbox": list(bbox),
        "status": "QUEUED", "queued_at": _now(),
        "started_at": None, "finished_at": None,
        "message": "Recorte aguardando processamento no servidor.",
        "result": None,
    }


def safe_status(job: dict) -> dict:
    """Resposta sem URLs, diretórios físicos ou detalhes internos do worker."""
    return {k: job.get(k) for k in (
        "id", "piece_id", "item_id", "collection", "status",
        "queued_at", "started_at", "finished_at", "message",
    )}


def queued_jobs() -> list[Path]:
    paths = []
    for p in jobs_root().glob("*.json"):
        try:
            job = read_job(UUID(p.stem))
            if job.get("status") == "QUEUED":
                paths.append((str(job.get("queued_at") or ""), p))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return [path for _, path in sorted(paths, key=lambda value: value[0])]


def prune_terminal_jobs(*, days: int = 90, now: datetime | None = None) -> int:
    """Remove apenas metadados de jobs antigos e terminais.

    Nunca apaga GeoTIFF, XML, PDF ou jobs ativos. Um trabalho novo pode
    ser recriado se o histórico de status tiver expirado.
    """
    if days < 30:
        raise ValueError("Retenção de jobs PS4 não pode ser inferior a 30 dias.")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    removed = 0
    for path in jobs_root().glob("*.json"):
        try:
            job = read_job(UUID(path.stem))
            if job.get("status") not in TERMINAL:
                continue
            finished = job.get("finished_at")
            if not isinstance(finished, str):
                continue
            end = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            if end.tzinfo is None or end >= cutoff:
                continue
            path.unlink()
            removed += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return removed
