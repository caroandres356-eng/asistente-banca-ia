"""DAG: reindexa Chroma cuando cambian los documentos de data/docs.

Airflow no carga modelos ni toca Chroma. Solo calcula un hash de los documentos y,
si cambió, le pide a la API que reindexe y verifica el resultado.
"""
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

try:
    from airflow.decorators import dag, task  # type: ignore[import-not-found]
    from airflow.models import Variable  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - solo para entornos sin Airflow instalado localmente
    class _TaskDecorator:
        def __call__(self, *args, **kwargs):
            def decorator(fn):
                return fn
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return args[0]
            return decorator

        def __getattr__(self, name):
            if name == "short_circuit":
                return self
            return self

    def dag(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    task = _TaskDecorator()

    class Variable:  # type: ignore[no-redef]
        @staticmethod
        def get(key, default=None, **_kwargs):
            return default

        @staticmethod
        def set(key, value, **_kwargs):
            return None

API_URL = os.environ.get("API_URL", "http://host.docker.internal:8000")
API_KEY = os.environ.get("REINDEX_KEY", "")
DOCS = Path("/opt/airflow/docs")                 # data/docs montado en solo lectura
CLAVE_HASH = "hash_docs_indexados"               # Variable de Airflow con el último hash indexado


@dag(
    dag_id="reindexar_documentos",
    schedule="0 3 * * *",                        # todos los días a las 3:00
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["banco", "rag"],
)
def reindexar_documentos():

    @task
    def calcular_hash() -> str:
        archivos = sorted(DOCS.glob("*.txt"))
        if not archivos:
            raise FileNotFoundError("No hay .txt en /opt/airflow/docs; revisa el volumen del compose")
        h = hashlib.sha256()
        for f in archivos:
            h.update(f.name.encode())
            h.update(f.read_bytes())
        return h.hexdigest()

    @task.short_circuit
    def hay_cambios(hash_actual: str) -> bool:
        # Si devuelve False, se omiten todas las tareas siguientes
        return hash_actual != Variable.get(CLAVE_HASH, default=None)

    @task
    def verificar_api():
        r = requests.get(f"{API_URL}/salud", timeout=15)
        r.raise_for_status()
        if r.json().get("estado") != "ok":
            raise RuntimeError(f"La API no está lista: {r.json()}")

    @task(retries=1)
    def reindexar() -> dict:
        r = requests.post(f"{API_URL}/reindexar", headers={"X-API-Key": API_KEY}, timeout=900)
        if not r.ok:
            raise RuntimeError(f"/reindexar respondió {r.status_code}: {r.text}")
        return r.json()

    @task
    def comprobar(resultado: dict):
        r = requests.get(f"{API_URL}/salud", timeout=15)
        r.raise_for_status()
        salud = r.json()
        if salud.get("estado") != "ok" or resultado["chunks"] == 0 or salud.get("chunks") != resultado["chunks"]:
            raise RuntimeError(f"Verificación fallida. Reindexado: {resultado}. Salud: {salud}")

    @task
    def guardar_hash(hash_actual: str):
        # Solo se llega aquí si todo lo anterior salió bien
        Variable.set(CLAVE_HASH, hash_actual)

    h: str = calcular_hash()
    cambio: Any = hay_cambios(h)
    api_lista: Any = verificar_api()
    resultado: Any = reindexar()
    verificado: Any = comprobar(resultado)
    guardado: Any = guardar_hash(h)

    _ = cambio >> api_lista >> resultado >> verificado >> guardado


reindexar_documentos()