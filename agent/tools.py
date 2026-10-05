import sqlite3
from functools import lru_cache
from rag.common import get_db
from agent.db import conectar

UMBRAL_RAG = 10.0   # distancia L2 máxima aceptable (provisional)


@lru_cache(maxsize=1)
def _base_vectorial():
    # Se carga una sola vez: abrir el modelo de embeddings es lo más lento
    return get_db()


# ---------- Herramienta 1: RAG (solo lectura) ----------
def tool_rag(pregunta, k=3):
    resultados = _base_vectorial().similarity_search_with_score(pregunta, k=k)
    mejor = resultados[0][1] if resultados else None
    buenos = [(d, dist) for d, dist in resultados if dist <= UMBRAL_RAG]
    contexto = [d.page_content for d, _ in buenos]
    fuentes = sorted({d.metadata["fuente"] for d, _ in buenos})
    return {"contexto": contexto, "fuentes": fuentes, "mejor_distancia": mejor}


# ---------- Herramienta 2: SQL de lectura ----------
def tool_estado_tarjetas(cliente_id):
    # Consulta fija y parametrizada. cliente_id viene de la sesión, no de la pregunta
    with conectar() as c:
        filas = c.execute(
            "SELECT id, ultimos4, tipo, estado FROM tarjetas WHERE cliente_id = ?",
            (cliente_id,)).fetchall()
    return [f"Tarjeta de {tipo} terminada en {u4}: {estado}"
            for _, u4, tipo, estado in filas]


# ---------- Herramienta 3: acción de escritura ----------
def tool_bloquear_tarjeta(cliente_id, tarjeta_id, aprobado_por):
    """Solo se llama después de la aprobación humana. Es idempotente y deja auditoría."""
    with conectar() as c:
        fila = c.execute(
            "SELECT estado FROM tarjetas WHERE id = ? AND cliente_id = ?",
            (tarjeta_id, cliente_id)).fetchone()
        if fila is None:
            resultado = "no_encontrada"          # no existe o no es de este cliente
        elif fila[0] == "bloqueada":
            resultado = "ya_bloqueada"           # reintento: no repite el efecto
        else:
            c.execute("UPDATE tarjetas SET estado = 'bloqueada' WHERE id = ? AND cliente_id = ?",
                      (tarjeta_id, cliente_id))
            resultado = "bloqueada"
        c.execute(
            "INSERT INTO auditoria (cliente_id, accion, tarjeta_id, aprobado_por, resultado) "
            "VALUES (?, 'bloquear_tarjeta', ?, ?, ?)",
            (cliente_id, tarjeta_id, aprobado_por, resultado))
    return resultado


if __name__ == "__main__":
    from agent.db import crear_base
    crear_base()

    print("RAG (real):", tool_rag("¿Cuánto puedo retirar al día en un cajero?"))
    print("RAG (fuera de tema):", tool_rag("¿Cuál es la capital de Francia?"))
    print("Tarjetas de Ana:", tool_estado_tarjetas(1))
    print("Bloquear tarjeta 1 de Ana:", tool_bloquear_tarjeta(1, 1, "asesor_01"))
    print("Repetir el bloqueo:", tool_bloquear_tarjeta(1, 1, "asesor_01"))
    print("Ana intenta bloquear la tarjeta 3 (de Luis):", tool_bloquear_tarjeta(1, 3, "asesor_01"))
    print("Tarjetas de Ana ahora:", tool_estado_tarjetas(1))