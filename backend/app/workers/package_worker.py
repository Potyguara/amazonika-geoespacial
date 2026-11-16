from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import Source
from app.services.importer import import_vector_file
from app.services.package_importer import import_package, inspect_package
from app.workers.ps4_inpe_worker import recover_jobs as recover_ps4_jobs, process_next_job as process_next_ps4_job
from app.services.ps4_inpe_queue import prune_terminal_jobs
from app.services.inpe_ps4_import import cleanup_stale_crop_temporaries


POLL_SECONDS = 3


def _root() -> Path:
    path = get_settings().storage_dir / ".chunk_uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(meta_path: Path) -> dict:
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _write(meta_path: Path, meta: dict) -> None:
    temporary = meta_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(meta, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temporary.replace(meta_path)


def _update(meta_path: Path, **changes) -> dict:
    meta = _read(meta_path)
    meta.update(changes)
    _write(meta_path, meta)
    return meta


def _classify_error(exc: Exception) -> dict:
    text = str(exc)
    lowered = text.lower()

    if "statement timeout" in lowered or "querycanceled" in lowered:
        return {
            "error_code": "DATABASE_STATEMENT_TIMEOUT",
            "error_title": "Tempo limite do banco de dados",
            "error_detail": (
                "A operação no banco ultrapassou o tempo permitido."
            ),
            "error_retryable": True,
        }

    if (
        "no space left on device" in lowered
        or "disk full" in lowered
        or "could not extend file" in lowered
    ):
        return {
            "error_code": "INSUFFICIENT_DISK_SPACE",
            "error_title": "Espaço insuficiente no servidor",
            "error_detail": (
                "O servidor não possui espaço livre suficiente "
                "para concluir esta importação."
            ),
            "error_retryable": True,
        }

    if "falha gdal" in lowered or "ogr2ogr" in lowered:
        return {
            "error_code": "GDAL_IMPORT_ERROR",
            "error_title": "Falha ao importar a camada vetorial",
            "error_detail": (
                "O GDAL não conseguiu converter uma das camadas "
                "do GeoPackage para o PostGIS."
            ),
            "error_retryable": True,
        }

    if "camadas ausentes" in lowered or "pacote está incompleto" in lowered:
        return {
            "error_code": "PACKAGE_INCOMPLETE",
            "error_title": "Pacote incompatível",
            "error_detail": text[:2000],
            "error_retryable": False,
        }

    return {
        "error_code": "PACKAGE_PROCESSING_ERROR",
        "error_title": "Falha no processamento do pacote",
        "error_detail": text[:2000],
        "error_retryable": True,
    }


def _recover_interrupted_jobs() -> None:
    for meta_path in _root().glob("package_*/meta.json"):
        try:
            meta = _read(meta_path)
        except Exception:
            continue

        if meta.get("status") != "PROCESSING":
            continue

        stored = Path(str(meta.get("stored_path") or ""))

        meta.update(
            {
                "status": "FAILED",
                "processing_stage": "Processamento interrompido",
                "processing_finished_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "error_code": "WORKER_INTERRUPTED",
                "error_title": "Processamento interrompido",
                "error_detail": (
                    "O worker foi reiniciado antes da conclusão. "
                    "O arquivo foi preservado e pode ser processado novamente."
                ),
                "error_retryable": stored.exists(),
                "error": (
                    "O processamento foi interrompido antes da conclusão."
                ),
            }
        )

        _write(meta_path, meta)



def _vector_meta_paths():
    for meta_path in _root().glob("*/meta.json"):
        # Pacotes compostos continuam usando a lógica própria.
        if meta_path.parent.name.startswith("package_"):
            continue
        yield meta_path


def _recover_interrupted_vector_jobs() -> None:
    for meta_path in _vector_meta_paths():
        try:
            meta = _read(meta_path)
        except Exception:
            continue

        if meta.get("status") != "PROCESSING":
            continue

        stored = Path(str(meta.get("stored_path") or ""))

        meta.update(
            {
                "status": "FAILED",
                "processing_code": "WORKER_INTERRUPTED",
                "processing_stage": "Processamento interrompido",
                "processing_finished_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "error": (
                    "O processamento vetorial foi interrompido. "
                    "O arquivo foi preservado para nova tentativa."
                ),
                "error_code": "WORKER_INTERRUPTED",
                "error_title": "Processamento interrompido",
                "error_detail": (
                    "O worker foi reiniciado antes da conclusão."
                ),
                "error_retryable": stored.exists(),
            }
        )

        _write(meta_path, meta)


def _next_queued_vector_job() -> Path | None:
    candidates = []

    for meta_path in _vector_meta_paths():
        try:
            meta = _read(meta_path)
        except Exception:
            continue

        if meta.get("status") != "QUEUED":
            continue

        if not meta.get("source_id"):
            continue

        candidates.append(
            (
                str(
                    meta.get("queued_at")
                    or meta.get("created_at")
                    or ""
                ),
                meta_path,
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _classify_vector_error(exc: Exception) -> dict:
    message = str(exc)
    lowered = message.lower()

    if (
        "no space left on device" in lowered
        or "disk full" in lowered
        or "could not extend file" in lowered
    ):
        code = "INSUFFICIENT_DISK_SPACE"
        title = "Espaço insuficiente no servidor"
    elif (
        "statement timeout" in lowered
        or "querycanceled" in lowered
    ):
        code = "DATABASE_STATEMENT_TIMEOUT"
        title = "Tempo limite do banco de dados"
    elif "ogr2ogr" in lowered or "gdal" in lowered:
        code = "GDAL_IMPORT_ERROR"
        title = "Falha na conversão do vetor"
    else:
        code = "VECTOR_PROCESSING_ERROR"
        title = "Falha no processamento vetorial"

    return {
        "error_code": code,
        "error_title": title,
        "error_detail": message[:2000],
        "error_retryable": True,
    }


def _process_vector(meta_path: Path) -> None:
    db = SessionLocal()

    try:
        meta = _read(meta_path)

        upload_id = str(meta.get("upload_id") or "")
        source_id = UUID(str(meta.get("source_id")))
        stored_path = Path(str(meta.get("stored_path") or ""))
        filename = str(meta.get("filename") or stored_path.name)
        layer_name = meta.get("layer_name") or None
        reference_raw = str(
            meta.get("reference_date") or ""
        ).strip()

        if not stored_path.exists():
            raise RuntimeError(
                "O arquivo vetorial armazenado não foi encontrado."
            )

        source = db.get(Source, source_id)

        if not source:
            raise RuntimeError(
                "A fonte associada ao upload não foi encontrada."
            )

        reference_date = (
            date.fromisoformat(reference_raw)
            if reference_raw
            else None
        )

        meta.update(
            {
                "status": "PROCESSING",
                "processing_code": "IMPORTING_VECTOR",
                "processing_stage": "Importando vetor para o PostGIS",
                "progress_percent": 99,
                "processing_started_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "processing_finished_at": None,
                "error": None,
                "error_code": None,
                "error_title": None,
                "error_detail": None,
                "error_retryable": False,
            }
        )

        _write(meta_path, meta)

        version = import_vector_file(
            db,
            source,
            stored_path,
            reference_date,
            layer_name,
            filename,
        )

        file_removed = False
        cleanup_warning = None

        try:
            stored_path.unlink(missing_ok=True)
            file_removed = True
        except Exception as cleanup_exc:
            cleanup_warning = (
                "A importação foi concluída, mas o arquivo físico "
                f"não pôde ser removido: {cleanup_exc}"
            )

        meta = _read(meta_path)

        meta.update(
            {
                "status": "READY",
                "processing_code": "READY",
                "processing_stage": "Concluído",
                "progress_percent": 100,
                "processing_finished_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "result": {
                    "source_id": str(source.id),
                    "source_name": source.name,
                    "version_id": str(version.id),
                    "feature_count": int(
                        version.feature_count or 0
                    ),
                },
                "error": None,
                "error_code": None,
                "error_title": None,
                "error_detail": None,
                "error_retryable": False,
                "file_removed_after_processing": file_removed,
                "cleanup_warning": cleanup_warning,
            }
        )

        if file_removed:
            meta["stored_path"] = None

        _write(meta_path, meta)

        print(
            f"[package-worker] VECTOR READY "
            f"{upload_id} {source.name}",
            flush=True,
        )

    except Exception as exc:
        db.rollback()

        classified = _classify_vector_error(exc)

        try:
            meta = _read(meta_path)

            meta.update(
                {
                    "status": "FAILED",
                    "processing_code": "FAILED",
                    "processing_stage": (
                        "Falha no processamento vetorial"
                    ),
                    "processing_finished_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "error": str(exc)[:4000],
                    **classified,
                }
            )

            _write(meta_path, meta)

        except Exception:
            pass

        print(
            f"[package-worker] VECTOR FAILED "
            f"{meta_path}: {exc}",
            flush=True,
        )

    finally:
        db.close()


def _next_queued_job() -> Path | None:
    candidates = []

    for meta_path in _root().glob("package_*/meta.json"):
        try:
            meta = _read(meta_path)
        except Exception:
            continue

        if meta.get("status") == "QUEUED":
            candidates.append(
                (
                    str(meta.get("queued_at") or meta.get("created_at") or ""),
                    meta_path,
                )
            )

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _process(meta_path: Path) -> None:
    db = SessionLocal()

    try:
        meta = _read(meta_path)

        upload_id = str(meta.get("upload_id") or "")
        group = str(meta.get("group") or "").strip().upper()
        stored_path = Path(str(meta.get("stored_path") or ""))
        reference_raw = str(meta.get("reference_date") or "").strip()

        if not stored_path.exists():
            raise RuntimeError(
                "O arquivo armazenado do pacote não foi encontrado."
            )

        if not reference_raw:
            raise RuntimeError(
                "A data de referência do pacote não foi informada."
            )

        reference_date = date.fromisoformat(reference_raw)

        meta.update(
            {
                "status": "PROCESSING",
                "processing_stage": "Validando GeoPackage",
                "processing_code": "VALIDATING",
                "progress_percent": 2,
                "processing_started_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "processing_finished_at": None,
                "error": None,
                "error_code": None,
                "error_title": None,
                "error_detail": None,
                "error_retryable": False,
            }
        )
        _write(meta_path, meta)

        inspection = inspect_package(
            db,
            group,
            stored_path,
        )

        meta = _read(meta_path)
        meta["inspection"] = inspection
        _write(meta_path, meta)

        if not inspection.get("valid"):
            missing = ", ".join(
                inspection.get("missing_layers") or []
            )
            raise RuntimeError(
                f"O pacote está incompleto. Camadas ausentes: {missing}"
            )

        def progress_callback(payload: dict) -> None:
            current = _read(meta_path)

            current.update(
                {
                    "status": "PROCESSING",
                    "processing_stage": payload.get(
                        "processing_stage",
                        current.get("processing_stage"),
                    ),
                    "processing_code": payload.get(
                        "processing_code",
                        current.get("processing_code"),
                    ),
                    "progress_percent": payload.get(
                        "progress_percent",
                        current.get("progress_percent", 0),
                    ),
                    "current_layer": payload.get(
                        "current_layer",
                        current.get("current_layer"),
                    ),
                    "current_source": payload.get(
                        "current_source",
                        current.get("current_source"),
                    ),
                    "current_layer_index": payload.get(
                        "current_layer_index",
                        current.get("current_layer_index"),
                    ),
                    "total_layers": payload.get(
                        "total_layers",
                        current.get("total_layers"),
                    ),
                    "current_layer_total_features": payload.get(
                        "current_layer_total_features",
                        current.get("current_layer_total_features"),
                    ),
                    "completed_layers": payload.get(
                        "completed_layers",
                        current.get("completed_layers", []),
                    ),
                }
            )

            _write(meta_path, current)

        result = import_package(
            db,
            group,
            stored_path,
            reference_date,
            progress_callback=progress_callback,
        )

        file_removed = False
        cleanup_warning = None

        try:
            stored_path.unlink(missing_ok=True)
            file_removed = True
        except Exception as cleanup_exc:
            cleanup_warning = (
                "A importação foi concluída, mas o arquivo físico "
                f"não pôde ser removido: {cleanup_exc}"
            )

        meta = _read(meta_path)

        meta.update(
            {
                "status": "READY",
                "processing_code": "READY",
                "processing_stage": "Concluído",
                "progress_percent": 100,
                "processing_finished_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "result": result,
                "error": None,
                "error_code": None,
                "error_title": None,
                "error_detail": None,
                "error_retryable": False,
                "file_removed_after_processing": file_removed,
                "cleanup_warning": cleanup_warning,
            }
        )

        if file_removed:
            meta["stored_path"] = None

        _write(meta_path, meta)

        print(
            f"[package-worker] READY {upload_id} {group}",
            flush=True,
        )

    except Exception as exc:
        db.rollback()

        classified = _classify_error(exc)

        try:
            meta = _read(meta_path)

            meta.update(
                {
                    "status": "FAILED",
                    "processing_code": "FAILED",
                    "processing_stage": "Falha no processamento",
                    "processing_finished_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "error": str(exc)[:4000],
                    **classified,
                }
            )

            _write(meta_path, meta)
        except Exception:
            pass

        print(
            f"[package-worker] FAILED {meta_path}: {exc}",
            flush=True,
        )

    finally:
        db.close()


def main() -> None:
    print("[package-worker] iniciado", flush=True)

    _recover_interrupted_jobs()
    _recover_interrupted_vector_jobs()
    recover_ps4_jobs()
    try:
        removed = cleanup_stale_crop_temporaries()
        print(f"[package-worker] PS4 temporários antigos limpos: {removed}", flush=True)
    except Exception as exc:
        print(f"[package-worker] limpeza de temporários PS4 ignorada: {exc}", flush=True)
    try:
        count = prune_terminal_jobs(days=90)
        print(f"[package-worker] PS4 arquivos de status antigos eliminados: {count}", flush=True)
    except Exception as exc:
        print(f"[package-worker] limpeza de status PS4 ignorada: {exc}", flush=True)

    while True:
        # Pacotes compostos continuam com prioridade, pois podem
        # representar milhões de feições e várias fontes.
        job = _next_queued_job()

        if job is not None:
            _process(job)
            continue

        vector_job = _next_queued_vector_job()

        if vector_job is not None:
            _process_vector(vector_job)
            continue

        # Recortes CBERS são processados em separado do HTTP, aproveitando o
        # worker já implantado e o volume compartilhado uploads_data.
        if process_next_ps4_job():
            continue

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
