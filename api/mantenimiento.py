"""Endpoints de mantenimiento: estado del índice y reindexación.

Los usa Airflow. La reindexación corre rag/ingest.py como un proceso aparte, así que
no hace falta tocar ese archivo.
"""
import gc
import importlib
import os
import re
import secrets
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from agent.tools import _base_vectorial

router = APIRouter(tags=["mantenimiento"])

RAIZ = Path(__file__).resolve().parent.parent          # raíz del repo
INGEST = RAIZ / "rag" / "ingest.py"
REINDEXANDO = threading.Lock()                          # evita dos reindexaciones a la vez


def _contar_chunks() -> int:
    return len(_base_vectorial().get()["ids"])


def _liberar_chroma() -> None:
    """Suelta la conexión abierta a chroma_db.

    ingest.py borra esa carpeta, y en Windows no se puede borrar un archivo que otro
    proceso (esta API) tiene abierto.
    """
    _base_vectorial.cache_clear()
    for ruta in ("chromadb.api.shared_system_client", "chromadb.api.client"):
        try:
            importlib.import_module(ruta).SharedSystemClient.clear_system_cache()
            break
        except (ImportError, AttributeError):
            continue
    gc.collect()


@router.get("/salud")
def salud():
    if REINDEXANDO.locked():
        return {"estado": "reindexando"}
    return {"estado": "ok", "chunks": _contar_chunks()}


@router.post("/reindexar")
def reindexar(x_api_key: Optional[str] = Header(default=None)):
    clave = os.environ.get("REINDEX_KEY")
    if not clave:
        raise HTTPException(status_code=503, detail="REINDEX_KEY no está configurada en el servidor")
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), clave.encode()):
        raise HTTPException(status_code=401, detail="Clave inválida")
    if not REINDEXANDO.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Ya hay una reindexación en curso")

    try:
        _liberar_chroma()
        try:
            p = subprocess.run([sys.executable, str(INGEST)], cwd=RAIZ,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="ingest.py superó los 15 minutos")

        if p.returncode != 0:
            raise HTTPException(status_code=500, detail=f"ingest.py falló: {p.stderr[-500:]}")

        m = re.search(r"Indexados (\d+) chunks de (\d+) documentos", p.stdout)
        if not m:
            raise HTTPException(status_code=500, detail="No se pudo leer el resultado de ingest.py")
        esperados, documentos = int(m.group(1)), int(m.group(2))

        # Reabre Chroma con el índice nuevo y comprueba que coincide con lo que se indexó.
        # Si Windows no dejó borrar la carpeta vieja, habría chunks duplicados y no coincidiría.
        reales = _contar_chunks()
        if reales != esperados:
            raise HTTPException(
                status_code=500,
                detail=(f"Índice inconsistente: se indexaron {esperados} chunks y hay {reales}. "
                        "Detén la API, corre `python rag/ingest.py` y vuelve a arrancarla."))
        return {"estado": "ok", "chunks": reales, "documentos": documentos}
    finally:
        REINDEXANDO.release()