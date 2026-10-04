"""API del asistente de Banco Andino.

Ejecutar desde la raíz del repo (para que banco.db y chroma_db se encuentren):
    uvicorn api.main:app
No uses --reload: recargaría los modelos y borraría los pendientes en memoria.
"""
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from langgraph.types import Command
from pydantic import BaseModel, Field

from functools import lru_cache

import rag.common as rc

# get_emb() crea un modelo nuevo en cada llamada y el nodo 'clasificar' lo llama en
# cada pregunta. Se envuelve aquí, ANTES de importar agent.*, para compartir una sola
# instancia sin tocar rag/common.py.
rc.get_emb = lru_cache(maxsize=1)(rc.get_emb)

from agent.db import DB_PATH, conectar, crear_base  # noqa: E402
from agent.graph import grafo, cfg, _llm, _vectores_ejemplo  # noqa: E402
from agent.tools import _base_vectorial  # noqa: E402

# Acciones esperando a un asesor. Vive en memoria, igual que MemorySaver:
# si reinicias la API se pierden (en producción irían a un checkpointer persistente).
PENDIENTES: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # crear_base() borra y recrea las tablas, así que solo se llama si no existe el archivo
    if not os.path.exists(DB_PATH):
        crear_base()
    # Precarga los modelos para que la primera petición no sea lenta
    _llm()
    _vectores_ejemplo()
    _base_vectorial()
    yield


app = FastAPI(title="Asistente Banco Andino", lifespan=lifespan)


class Pregunta(BaseModel):
    # En producción cliente_id saldría del token de sesión, no del cuerpo de la petición
    cliente_id: int
    pregunta: str = Field(min_length=3, max_length=500)


class Decision(BaseModel):
    aprobado: bool
    asesor: str = Field(min_length=1, max_length=50)


def _resultado(thread_id: str, r: dict) -> dict:
    if "__interrupt__" in r:
        info = r["__interrupt__"][0].value      # {"accion": ..., "cliente_id": ...}
        PENDIENTES[thread_id] = info
        return {"thread_id": thread_id,
                "estado": "pendiente_aprobacion",
                "respuesta": "Su solicitud fue enviada a un asesor para su aprobación.",
                "accion": info["accion"]}
    return {"thread_id": thread_id,
            "estado": "respondida",
            "respuesta": r.get("respuesta"),
            "intencion": r.get("intencion"),
            "fuentes": r.get("fuentes", []),
            "traza": r.get("traza")}


@app.post("/preguntar")
def preguntar(p: Pregunta):
    with conectar() as c:
        existe = c.execute("SELECT 1 FROM clientes WHERE id = ?", (p.cliente_id,)).fetchone()
    if existe is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    thread_id = str(uuid.uuid4())
    r = grafo.invoke({"cliente_id": p.cliente_id, "pregunta": p.pregunta,
                      "inicio": time.time()}, cfg(thread_id))
    return _resultado(thread_id, r)


@app.get("/pendientes")
def pendientes():
    return [{"thread_id": t, **info} for t, info in PENDIENTES.items()]


@app.post("/pendientes/{thread_id}/decision")
def decidir(thread_id: str, d: Decision):
    # pop evita que dos asesores resuelvan la misma acción
    info = PENDIENTES.pop(thread_id, None)
    if info is None:
        raise HTTPException(status_code=404, detail="No hay una acción pendiente con ese thread_id")
    try:
        r = grafo.invoke(Command(resume=d.model_dump()), cfg(thread_id))
    except Exception:
        PENDIENTES[thread_id] = info            # si falla, la acción sigue pendiente
        raise
    return _resultado(thread_id, r)