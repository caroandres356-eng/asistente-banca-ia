# Construcción y ejecución de ejemplo:
# docker build -t banco-api .
# docker run -p 8000:8000 -e REINDEX_KEY=tu-clave banco-api

# Python 3.14 coincide con la versión 3.14.3 del entorno virtual del proyecto.
FROM python:3.14-slim

# La API espera encontrar banco.db, chroma_db y data/docs desde /app.
WORKDIR /app

# La caché compartida permite precargar modelos y leerlos como usuario no root.
ENV HF_HOME=/opt/huggingface

# Torch se instala primero desde el índice CPU para evitar ruedas CUDA.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

# Se copia el manifiesto antes del código para reutilizar la caché de dependencias.
COPY requirements.txt /app/requirements.txt

# Se instalan las demás dependencias; torch ya está instalado desde el índice CPU.
RUN pip install --no-cache-dir -r requirements.txt

# Usuario sin privilegios y directorios escribibles para caché y base de datos.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /opt/huggingface \
    && chown -R app:app /app /opt/huggingface

# Solo se incluyen los módulos de la API y los documentos usados por el índice.
COPY --chown=app:app api/ /app/api/
COPY --chown=app:app agent/ /app/agent/
COPY --chown=app:app rag/ /app/rag/
COPY --chown=app:app data/docs/ /app/data/docs/

# La ingesta se ejecuta como script para que "from common import ..." funcione.
RUN python rag/ingest.py

# Los dos modelos se descargan durante el build, no al iniciar el contenedor.
RUN python -c "from transformers import AutoTokenizer, AutoModelForCausalLM; from sentence_transformers import SentenceTransformer; model = 'Qwen/Qwen2.5-0.5B-Instruct'; AutoTokenizer.from_pretrained(model); AutoModelForCausalLM.from_pretrained(model); SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# El usuario de ejecución puede actualizar el índice y crear banco.db en /app.
RUN chown -R app:app /app /opt/huggingface
USER app

# Puerto HTTP de FastAPI.
EXPOSE 8000

# Se inicia Uvicorn sin recarga automática para conservar el estado en memoria.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
