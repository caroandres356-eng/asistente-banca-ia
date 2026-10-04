import re
import time
from functools import lru_cache
from typing import Any, TypedDict, cast

import numpy as np
import torch
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from transformers import AutoTokenizer, AutoModelForCausalLM

from rag.common import get_emb
from agent.db import conectar
from agent.tools import tool_rag, tool_estado_tarjetas, tool_bloquear_tarjeta

BASE = "Qwen/Qwen2.5-0.5B-Instruct"
UMBRAL_ROUTER = 11.0   # distancia L2 máxima a una frase de ejemplo (PROVISIONAL, hay que calibrar)

SYSTEM = ("Eres el asistente virtual de Banco Andino. Responde de forma formal y cordial, "
          "usando únicamente el contexto entregado. Si el contexto no contiene la respuesta, "
          "indícalo. Empieza con 'Estimado cliente,' y termina con 'Cordialmente, Banco Andino.'")

EJEMPLOS = {
    "normativa": ["¿Cuánto cuesta transferir a otro banco?", "¿Cuál es el límite de retiro en cajero?",
                  "¿Cuántos días tienen para responder un reclamo?", "¿Cómo evito la cuota de manejo?",
                  "¿Cuánto cuesta reponer mi tarjeta?"],
    "consulta":  ["¿Está activa mi tarjeta?", "¿Qué tarjetas tengo?",
                  "¿Cuál es el estado de mi tarjeta?", "¿Mi tarjeta de crédito está bloqueada?"],
    "accion":    ["Quiero bloquear mi tarjeta", "Bloquéame la tarjeta, la perdí",
                  "Me robaron la tarjeta, bloquéala", "Necesito bloquear mi tarjeta de crédito"],
}


class Estado(TypedDict, total=False):
    cliente_id: int
    pregunta: str
    inicio: float
    intencion: str
    distancia_router: float
    contexto: list
    fuentes: list
    mejor_distancia: float
    accion: dict
    aprobado: bool
    aprobado_por: str
    respuesta: str
    traza: list


# ---------- Recursos que se cargan una sola vez ----------
@lru_cache(maxsize=1)
def _vectores_ejemplo():
    emb = get_emb()
    return {k: np.array(emb.embed_documents(v)) for k, v in EJEMPLOS.items()}


@lru_cache(maxsize=1)
def _llm():
    tok = AutoTokenizer.from_pretrained(BASE)
    modelo = AutoModelForCausalLM.from_pretrained(BASE)
    modelo.eval()
    return tok, modelo


def _traza(s, nodo):
    return (s.get("traza") or []) + [nodo]


# ---------- Nodos ----------
def clasificar(s):
    q = np.array(get_emb().embed_query(s["pregunta"]))
    mejor, mejor_d = "otro", float("inf")
    for intencion, vecs in _vectores_ejemplo().items():
        d = float(((vecs - q) ** 2).sum(axis=1).min())   # L2 al cuadrado, como Chroma
        if d < mejor_d:
            mejor, mejor_d = intencion, d
    if mejor_d > UMBRAL_ROUTER:
        mejor = "otro"
    return {"intencion": mejor, "distancia_router": mejor_d, "traza": _traza(s, "clasificar")}


def nodo_rag(s):
    r = tool_rag(s["pregunta"])
    return {"contexto": r["contexto"], "fuentes": r["fuentes"],
            "mejor_distancia": r["mejor_distancia"], "traza": _traza(s, "rag")}


def nodo_sql(s):
    return {"contexto": tool_estado_tarjetas(s["cliente_id"]), "fuentes": ["base_clientes"],
            "traza": _traza(s, "sql")}


def proponer(s):
    # Solo propone la acción; no la ejecuta. Lista cerrada: únicamente 'bloquear_tarjeta'
    with conectar() as c:
        tarjetas = c.execute("SELECT id, ultimos4 FROM tarjetas WHERE cliente_id = ?",
                             (s["cliente_id"],)).fetchall()
    m = re.search(r"\b(\d{4})\b", s["pregunta"])
    elegida = None
    if m:
        elegida = next((t for t in tarjetas if t[1] == m.group(1)), None)
    elif len(tarjetas) == 1:
        elegida = tarjetas[0]
    if elegida is None:
        return {"accion": None, "contexto": ["Se requiere indicar los últimos 4 dígitos de la tarjeta a bloquear."],
                "traza": _traza(s, "proponer")}
    return {"accion": {"tipo": "bloquear_tarjeta", "tarjeta_id": elegida[0], "ultimos4": elegida[1]},
            "traza": _traza(s, "proponer")}


def aprobacion(s):
    # Pausa el grafo hasta que un asesor reanude con Command(resume=...)
    decision = interrupt({"accion": s["accion"], "cliente_id": s["cliente_id"]})
    return {"aprobado": bool(decision.get("aprobado")),
            "aprobado_por": decision.get("asesor", "desconocido"),
            "traza": _traza(s, "aprobacion")}


def ejecutar(s):
    a = s["accion"]
    resultado = tool_bloquear_tarjeta(s["cliente_id"], a["tarjeta_id"], s["aprobado_por"])
    return {"contexto": [f"Resultado del bloqueo de la tarjeta terminada en {a['ultimos4']}: {resultado}."],
            "fuentes": ["auditoria"], "traza": _traza(s, "ejecutar")}


def cancelar(s):
    return {"contexto": ["La solicitud de bloqueo no fue aprobada por el asesor y no se realizó ningún cambio."],
            "traza": _traza(s, "cancelar")}


def fuera(s):
    return {"respuesta": "Estimado cliente, no puedo ayudarle con ese tema. Le sugiero comunicarse con un asesor. "
                         "Cordialmente, Banco Andino.",
            "contexto": [], "traza": _traza(s, "fuera")}


def redactar(s):
    tok, modelo = _llm()
    ctx = "\n".join(s.get("contexto") or []) or "(sin información disponible)"
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Contexto:\n{ctx}\n\nPregunta: {s['pregunta']}"}]
    texto = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    entrada = tok(texto, return_tensors="pt")
    modelo_generativo = cast(Any, modelo)
    with torch.no_grad():
        salida = modelo_generativo.generate(**entrada, max_new_tokens=150, do_sample=False)
    resp = tok.decode(salida[0][entrada["input_ids"].shape[1]:], skip_special_tokens=True)
    return {"respuesta": resp.strip(), "traza": _traza(s, "redactar")}


def registrar(s):
    ms = int((time.time() - s.get("inicio", time.time())) * 1000)
    with conectar() as c:
        c.execute("INSERT INTO consultas (cliente_id, pregunta, intencion, mejor_distancia, respondida, latencia_ms) "
                  "VALUES (?, ?, ?, ?, ?, ?)",
                  (s["cliente_id"], s["pregunta"], s.get("intencion"), s.get("mejor_distancia"),
                   1 if s.get("contexto") else 0, ms))
    return {"traza": _traza(s, "registrar")}


# ---------- Armado del grafo ----------
def construir():
    g = StateGraph(Estado)
    for nombre, fn in [("clasificar", clasificar), ("rag", nodo_rag), ("sql", nodo_sql),
                       ("proponer", proponer), ("aprobacion", aprobacion), ("ejecutar", ejecutar),
                       ("cancelar", cancelar), ("fuera", fuera), ("redactar", redactar),
                       ("registrar", registrar)]:
        g.add_node(nombre, fn)

    g.add_edge(START, "clasificar")
    g.add_conditional_edges("clasificar", lambda s: s["intencion"],
        {"normativa": "rag", "consulta": "sql", "accion": "proponer", "otro": "fuera"})
    g.add_edge("rag", "redactar")
    g.add_edge("sql", "redactar")
    g.add_conditional_edges("proponer", lambda s: "aprobacion" if s.get("accion") else "redactar",
        {"aprobacion": "aprobacion", "redactar": "redactar"})
    g.add_conditional_edges("aprobacion", lambda s: "ejecutar" if s.get("aprobado") else "cancelar",
        {"ejecutar": "ejecutar", "cancelar": "cancelar"})
    g.add_edge("ejecutar", "redactar")
    g.add_edge("cancelar", "redactar")
    g.add_edge("redactar", "registrar")
    g.add_edge("fuera", "registrar")
    g.add_edge("registrar", END)
    return g.compile(checkpointer=MemorySaver())


grafo = construir()


def cfg(thread_id) -> RunnableConfig:
    return cast(RunnableConfig, {"configurable": {"thread_id": thread_id}, "recursion_limit": 15})


if __name__ == "__main__":
    from agent.db import crear_base
    crear_base()

    def preguntar(cliente_id, pregunta, tid):
        r = grafo.invoke({"cliente_id": cliente_id, "pregunta": pregunta, "inicio": time.time()}, cfg(tid))
        print(f"\nP: {pregunta}")
        print("intención:", r.get("intencion"), "| distancia router:", round(r.get("distancia_router", -1), 2))
        return r

    r = preguntar(1, "¿Cuánto puedo retirar al día en un cajero?", "t1")
    print("R:", r["respuesta"], "| fuentes:", r.get("fuentes"))

    r = preguntar(1, "¿Cuál es la capital de Francia?", "t2")
    print("R:", r["respuesta"])

    r = preguntar(1, "¿Está activa mi tarjeta?", "t3")
    print("R:", r["respuesta"])

    r = preguntar(1, "Bloquéame la tarjeta 4821, la perdí", "t4")
    print("¿Pausado?", "__interrupt__" in r, "| traza hasta ahora:", r.get("traza"))
    r = grafo.invoke(Command(resume={"aprobado": True, "asesor": "asesor_01"}), cfg("t4"))
    print("R:", r["respuesta"])
    print("Traza final:", r["traza"])