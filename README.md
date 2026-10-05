# Asistente bancario con RAG y LangGraph

Asistente conversacional de demostración para Banco Andino. Responde consultas
basadas en documentos del banco, consulta tarjetas ficticias en SQLite y permite
proponer el bloqueo de una tarjeta con aprobación humana. La API se implementa
con FastAPI; LangGraph coordina las decisiones y los pasos del asistente; Chroma
guarda el índice vectorial de los documentos. Apache Airflow revisa los documentos
y solicita una reindexación cuando detecta cambios.

> **Alcance:** este repositorio es un prototipo educativo. Los clientes y las
> tarjetas son datos ficticios. La API no autentica al cliente: `cliente_id` se
> recibe en el cuerpo de la petición y no debe usarse así en un sistema real.
> El bloqueo requiere aprobación en el flujo, pero el prototipo no reemplaza los
> controles, la identidad ni las auditorías de un banco real.

## Tabla de contenido

- [Arquitectura](#arquitectura)
- [Tecnologías y herramientas](#tecnologías-y-herramientas)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Requisitos previos](#requisitos-previos)
- [Instalación y ejecución local](#instalación-y-ejecución-local)
- [Flujo de una pregunta](#flujo-de-una-pregunta)
- [Flujo RAG e ingesta de documentos](#flujo-rag-e-ingesta-de-documentos)
- [API HTTP](#api-http)
- [Aprobación de una acción](#aprobación-de-una-acción)
- [Orquestación con Airflow](#orquestación-con-airflow)
- [Ejecución con Docker](#ejecución-con-docker)
- [Datos y persistencia](#datos-y-persistencia)
- [Configuración y seguridad](#configuración-y-seguridad)
- [Solución de problemas](#solución-de-problemas)
- [Trabajo futuro](#trabajo-futuro)

## Arquitectura

```text
Cliente HTTP
    |
    v
FastAPI (api/main.py)
    |
    +--> LangGraph (agent/graph.py)
    |       |
    |       +--> Router semántico con embeddings
    |       +--> RAG: búsqueda en Chroma (rag/common.py, agent/tools.py)
    |       +--> Consulta de tarjetas en SQLite (agent/db.py)
    |       +--> Bloqueo propuesto y pausa para aprobación humana
    |       +--> Redacción con Qwen
    |
    +--> API de mantenimiento (api/mantenimiento.py)
             |
             +--> /salud
             +--> /reindexar -> rag/ingest.py -> Chroma

Airflow (airflow/)
    |
    +--> calcula un hash de data/docs/*.txt
    +--> si cambió, comprueba la API y solicita /reindexar
    +--> comprueba el índice y guarda el hash en una Variable
```

La API y Airflow son procesos separados. Airflow no carga modelos ni accede
directamente a Chroma: monta los documentos en solo lectura y coordina la
reindexación por HTTP. La API ejecuta `rag/ingest.py` como un subproceso.

## Tecnologías y herramientas

| Herramienta | Uso en el proyecto |
| --- | --- |
| Python | Lenguaje de la API, el grafo, la ingesta y el DAG. El `.venv` revisado usa Python 3.14.3. |
| FastAPI | Define los endpoints HTTP y el ciclo de vida de carga de modelos. |
| Uvicorn | Servidor ASGI que publica FastAPI en el puerto 8000. |
| LangGraph | Controla el estado y el enrutamiento entre consulta normativa, consulta de tarjetas, acciones y respuesta. |
| LangChain | Integra embeddings, documentos, divisores de texto y el almacén vectorial. |
| Chroma | Almacena embeddings y fragmentos de los documentos para búsqueda semántica. |
| Hugging Face Transformers | Carga el modelo causal Qwen para redactar respuestas. |
| Sentence Transformers | Proporciona el modelo de embeddings multilingüe. |
| SQLite | Guarda clientes, tarjetas, auditoría y registro de consultas en `banco.db`. |
| Apache Airflow | Programa y supervisa la detección de cambios y la reindexación diaria. |
| Docker / Docker Compose | Empaqueta la API y ejecuta localmente los servicios de Airflow. |

Las dependencias Python se declaran en `requirements.txt`. Los modelos utilizados
son `Qwen/Qwen2.5-0.5B-Instruct` y
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

## Estructura del repositorio

```text
.
├── agent/
│   ├── db.py                 # conexión, creación de tablas y datos de ejemplo
│   ├── graph.py              # grafo, router semántico y aprobación
│   └── tools.py              # herramientas RAG, SQL y bloqueo
├── api/
│   ├── main.py               # endpoints del asistente y ciclo de vida
│   └── mantenimiento.py      # salud y reindexación protegida por clave
├── airflow/
│   ├── dags/
│   │   └── reindexar_docs.py # DAG diario de detección y reindexación
│   └── docker-compose.yaml   # Airflow local con LocalExecutor y PostgreSQL
├── data/
│   ├── docs/                 # fuentes de conocimiento incluidas en el proyecto
│   └── finetune/             # datos de entrenamiento
├── rag/
│   ├── common.py             # modelo de embeddings y acceso a Chroma
│   ├── ingest.py             # fragmenta e indexa los documentos
│   └── query.py              # consulta manual del índice
├── Dockerfile                # imagen de la API, no de Airflow
├── .dockerignore
├── .gitignore
└── requirements.txt
```

Los documentos actuales de `data/docs/` son políticas de tarjetas, retiros y
transferencias, y una circular. El índice no reemplaza los documentos: se
regenera a partir de ellos.

## Requisitos previos

- Python 3.14 para coincidir con el entorno virtual actual. Para otras versiones,
  comprueba antes la compatibilidad de PyTorch y de las dependencias.
- Git para obtener el repositorio.
- Conexión a Internet la primera vez para instalar paquetes y descargar los
  modelos de Hugging Face.
- Docker Engine/Desktop para los pasos de contenedores.
- Docker Compose v2 para iniciar Airflow.

Los modelos descargados ocupan espacio y requieren memoria. La inferencia se
configura en CPU en la imagen de la API; el tiempo de respuesta depende del
hardware disponible.

## Instalación y ejecución local

Ejecuta los siguientes comandos desde la raíz del repositorio.

### Windows PowerShell

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno, puedes invocar directamente
`.venv\Scripts\python.exe` y `.venv\Scripts\uvicorn.exe` sin cambiar la política
de ejecución de Windows.

### Linux / macOS

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r requirements.txt
```

### Preparar los datos y arrancar la API

La API crea `banco.db` con los datos ficticios si el archivo no existe. Para
crear o reconstruir explícitamente la base de datos, ejecuta:

```bash
python -m agent.db
```

> `agent.db.crear_base()` elimina y vuelve a crear las tablas y sus datos. No
> uses ese comando si quieres conservar cambios hechos a la base de datos local.

Construye el índice inicial y arranca la API:

```bash
python rag/ingest.py
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Ejecuta `rag/ingest.py` desde la raíz y como script por ruta: importa `common`
sin prefijo de paquete y utiliza `data/docs/` y `chroma_db/` relativos al
directorio actual. La API también espera que el directorio actual sea la raíz.
No uses `--reload`: los modelos se vuelven a cargar y las aprobaciones pendientes
se mantienen solo en memoria.

La primera carga puede tardar mientras se descargan los modelos. Cuando el
servidor esté disponible, abre `http://localhost:8000/docs` para explorar y
probar la API interactiva de FastAPI.

### Consulta manual del índice

Con el entorno virtual activo y desde la raíz:

```bash
python rag/query.py "¿Cuál es el límite de retiro en cajero?"
```

La herramienta imprime hasta tres coincidencias, con distancia, documento,
fragmento y una muestra del texto.

## Flujo de una pregunta

1. `POST /preguntar` recibe un `cliente_id` y una pregunta.
2. FastAPI valida la longitud de la pregunta y comprueba que el cliente exista.
3. LangGraph convierte la pregunta en un embedding y la compara con ejemplos de
   intención configurados en `agent/graph.py`.
4. El router decide uno de estos caminos:
   - **Normativa:** búsqueda semántica en Chroma. Solo se entregan al modelo los
     fragmentos dentro del umbral configurado.
   - **Consulta:** lectura parametrizada de las tarjetas del cliente en SQLite.
   - **Acción:** propone bloquear una tarjeta. Si es necesario, solicita sus
     últimos cuatro dígitos; no la bloquea todavía.
   - **Otro tema:** devuelve un mensaje de alcance limitado.
5. Para los caminos que redactan, Qwen recibe la pregunta y el contexto obtenido.
   El prompt le indica responder formalmente y basarse únicamente en ese
   contexto.
6. La consulta se registra en la tabla `consultas`.
7. Si el grafo pausó una acción, FastAPI guarda el identificador de hilo en la
   memoria del proceso y espera la decisión de un asesor.

Los umbrales del router y de la búsqueda RAG están marcados en el código como
provisionales; necesitan calibración con preguntas representativas.

## Flujo RAG e ingesta de documentos

1. Los documentos `.txt` se guardan en `data/docs/`.
2. `rag/ingest.py` recorre los archivos en orden alfabético.
3. `RecursiveCharacterTextSplitter` divide el texto en fragmentos de hasta 400
   caracteres, con un solapamiento de 60.
4. `HuggingFaceEmbeddings` calcula embeddings con
   `paraphrase-multilingual-MiniLM-L12-v2`.
5. Chroma crea el índice persistente en `chroma_db/`.
6. Al llegar una pregunta clasificada como normativa, la aplicación busca hasta
   tres fragmentos similares y devuelve contexto y fuentes.

**Importante:** la ingesta elimina la carpeta `chroma_db/` existente antes de
crear el índice. En la imagen Docker se genera durante el build a partir de los
documentos incluidos. Si los documentos cambian después, hay que reindexar
mediante la API o volver a construir el índice.

## API HTTP

La documentación interactiva está en `http://localhost:8000/docs` cuando la API
está iniciada.

### `POST /preguntar`

Ejemplo de petición:

```json
{
  "cliente_id": 1,
  "pregunta": "¿Está activa mi tarjeta?"
}
```

Una respuesta normal incluye `thread_id`, `estado`, `respuesta`, `intencion`,
`fuentes` y `traza`. Si el flujo requiere autorización, el estado será
`pendiente_aprobacion` e incluirá `accion`.

### `GET /pendientes`

Lista las acciones de bloqueo que esperan una decisión. La lista vive en memoria
y se pierde si la API se reinicia.

### `POST /pendientes/{thread_id}/decision`

Envía la aprobación o el rechazo asociado al identificador devuelto por
`/preguntar`. Ver [Aprobación de una acción](#aprobación-de-una-acción).

### `GET /salud`

Devuelve `{"estado":"ok","chunks":N}` si la API puede consultar Chroma, o indica
que está reindexando.

### `POST /reindexar`

Ejecuta la ingesta y devuelve el número de fragmentos y documentos indexados.
Requiere la cabecera `X-API-Key` cuyo valor debe coincidir con la variable de
entorno `REINDEX_KEY` del proceso de la API.

Ejemplo usando `curl`:

```bash
curl -X POST http://localhost:8000/preguntar \
  -H "Content-Type: application/json" \
  -d "{\"cliente_id\":1,\"pregunta\":\"¿Cuál es el límite diario de retiro?\"}"
```

En PowerShell, es más sencillo pasar el JSON como cadena entre comillas simples:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/preguntar `
  -ContentType "application/json" `
  -Body '{"cliente_id":1,"pregunta":"¿Cuál es el límite diario de retiro?"}'
```

## Aprobación de una acción

El bloqueo es una acción de escritura y no se ejecuta directamente al recibir la
pregunta:

1. El cliente solicita bloquear una tarjeta.
2. El grafo busca las tarjetas que pertenecen a ese cliente.
3. Si hay varias, identifica la tarjeta con los últimos cuatro dígitos indicados.
   Si no se puede seleccionar una tarjeta, pide esa información y no pausa para
   aprobación todavía.
4. LangGraph interrumpe el flujo y la API responde con un `thread_id` y los datos
   de la acción propuesta.
5. Un asesor envía la decisión a `POST /pendientes/{thread_id}/decision`.
6. Si se aprueba, el grafo actualiza la tarjeta y registra el resultado en
   `auditoria`. Si se rechaza, no se modifica la tarjeta.

Ejemplo de decisión:

```json
{
  "aprobado": true,
  "asesor": "asesor_01"
}
```

Puedes enviarla con `curl` sustituyendo `<THREAD_ID>` por el identificador
recibido:

```bash
curl -X POST http://localhost:8000/pendientes/<THREAD_ID>/decision \
  -H "Content-Type: application/json" \
  -d "{\"aprobado\":true,\"asesor\":\"asesor_01\"}"
```

El prototipo usa `MemorySaver` de LangGraph y un diccionario Python para las
acciones pendientes. Por tanto, reiniciar la API borra los hilos y las
aprobaciones pendientes; para producción se necesita un checkpointer persistente
y coordinación segura entre procesos.

## Orquestación con Airflow

El Compose de `airflow/docker-compose.yaml` levanta Airflow 3 con
`LocalExecutor`, PostgreSQL, servidor de API, scheduler y procesador de DAGs. Es
una configuración de desarrollo local, no una topología de producción. La
interfaz de Airflow se publica en `http://localhost:8080`.

### Configuración

1. Arranca la API en el puerto 8000, localmente o en el contenedor de API.
2. Comprueba que `airflow/.env` exista y tenga la configuración que espera el
   Compose, en particular el usuario de Airflow, una contraseña local y los
   valores `API_URL` y `REINDEX_KEY` para el DAG. No subas credenciales reales
   al repositorio.
3. `API_URL` debe ser alcanzable desde los contenedores de Airflow. Su valor por
   defecto en el DAG es `http://host.docker.internal:8000`; esto suele funcionar
   con Docker Desktop en Windows/macOS. En Linux puede requerir una dirección o
   una red Docker diferente.
4. El Compose monta `data/docs/` en `/opt/airflow/docs` en modo solo lectura.

### Inicio y parada

Desde el directorio `airflow/`:

```bash
docker compose up airflow-init
docker compose up -d
docker compose ps
docker compose logs -f airflow-scheduler airflow-dag-processor
```

Para apagar los servicios:

```bash
docker compose down
```

Para apagar y borrar también la base PostgreSQL de Airflow y su estado local,
usa `docker compose down --volumes`. Esto no es necesario para una parada normal.

### Qué hace el DAG

El DAG `reindexar_documentos` está programado diariamente a las 03:00 y no
ejecuta intervalos pasados (`catchup=False`):

1. Calcula SHA-256 sobre el nombre y contenido de cada `.txt` en
   `/opt/airflow/docs`.
2. Compara el resultado con la Variable de Airflow
   `hash_docs_indexados`.
3. Si el hash no cambió, `short_circuit` omite el resto de las tareas.
4. Si cambió, consulta `/salud` y verifica que la API esté lista.
5. Llama `POST /reindexar` enviando `X-API-Key`.
6. Consulta de nuevo `/salud` y comprueba que el número de fragmentos coincide
   con el resultado de la ingesta.
7. Solo si todo salió bien, actualiza `hash_docs_indexados`.

Si una tarea falla, Airflow reintenta según la política declarada en el DAG. El
hash no se guarda antes de completar la comprobación, por lo que la siguiente
ejecución puede volver a intentar la reindexación.

## Ejecución con Docker

El Dockerfile de la raíz construye **solo la API**. Airflow conserva su propio
Compose en `airflow/`.

```bash
docker build -t banco-api .
docker run --rm -p 8000:8000 -e REINDEX_KEY=define-una-clave-local banco-api
```

La imagen usa Python 3.14 slim, instala PyTorch desde el índice CPU, copia los
módulos `api/`, `agent/`, `rag/` y los documentos `data/docs/`, construye
`chroma_db/` durante el build y descarga los modelos de Hugging Face a la caché
de la imagen. Ejecuta Uvicorn sin `--reload` como usuario no root. El proceso
corre desde `/app`, necesario para las rutas relativas de SQLite y Chroma.

La clave de reindexación no se incluye en la imagen. El ejemplo usa un marcador:
reemplázalo por una clave local, y no la escribas en el Dockerfile ni la
comprometas en Git. Para producción, utiliza un gestor de secretos y configura
persistencia explícita si necesitas conservar la base SQLite, el índice o los
pendientes entre recreaciones del contenedor.

## Datos y persistencia

| Ruta / componente | Contenido | Comportamiento |
| --- | --- | --- |
| `data/docs/` | Documentos de conocimiento `.txt`. | Fuente del índice; Airflow los monta en solo lectura. |
| `data/finetune/` | Archivos de entrenamiento. | Se conservan en el repositorio, pero no se copian a la imagen de la API. |
| `chroma_db/` | Índice vectorial persistente. | Se regenera con `python rag/ingest.py`; se construye durante el build de Docker. |
| `banco.db` | Clientes, tarjetas, auditoría y consultas. | SQLite local; la API solo crea el esquema y datos iniciales si no existe el archivo. |
| `airflow` PostgreSQL | Metadatos y estado de Airflow. | Volumen administrado por Docker Compose. |
| Memoria del proceso API | Hilos y acciones pendientes. | No persiste tras reiniciar la API. |

## Configuración y seguridad

- `REINDEX_KEY` protege el endpoint de reindexación. Debe configurarse en la API
  y en el entorno del DAG con el mismo valor.
- `API_URL` indica al DAG dónde está la API; si no se configura, usa
  `http://host.docker.internal:8000`.
- No incluyas claves, contraseñas ni archivos `.env` con valores reales en Git.
- `cliente_id` se acepta directamente desde la petición y no demuestra la
  identidad del usuario. En una implementación real debe provenir de una sesión
  autenticada.
- El modelo genera texto a partir de contexto recuperado, pero este prototipo no
  constituye una garantía de exactitud. Valida respuestas antes de usarlo para
  decisiones financieras.
- La aprobación humana se representa con un endpoint y un nombre de asesor, pero
  no existe autenticación del asesor en este prototipo.
- La configuración de Airflow declara credenciales locales de desarrollo en su
  Compose/env. Sustitúyelas por secretos apropiados antes de cualquier uso
  compartido.

## Solución de problemas

### La API no encuentra `chroma_db` o `banco.db`

Arranca Uvicorn desde la raíz del repositorio. En Docker, el `WORKDIR` es `/app`.
Comprueba que el índice se haya creado ejecutando `python rag/ingest.py`.

### La ingesta falla al importar `common`

Ejecuta `python rag/ingest.py` como script y desde la raíz. No lo ejecutes como
`python -m rag.ingest` sin adaptar primero sus imports.

### Airflow no detecta los documentos

Verifica que `data/docs/` tenga archivos `.txt` y que el volumen esté montado.
La tarea calcula el hash solo de los archivos `.txt` directamente dentro de
`data/docs/`.

### Airflow no alcanza `/salud` o `/reindexar`

Confirma que la API esté levantada y que `API_URL` sea accesible desde los
contenedores, no solo desde el navegador del host. Verifica también que la
variable `REINDEX_KEY` coincida en el servicio de API y en Airflow.

### El DAG no vuelve a indexar

El DAG solo llama a la API cuando el hash difiere de la Variable
`hash_docs_indexados`. Para una ejecución manual, usa la interfaz de Airflow y
confirma que los documentos hayan cambiado; no borres el índice compartido
mientras la API esté sirviendo consultas.

### El bloqueo se pierde al reiniciar la API

Es el comportamiento actual: los checkpointers y las acciones pendientes están
en memoria. No reinicies la API mientras haya acciones que deban resolverse.

## Trabajo futuro

- Autenticar clientes y asesores; derivar el cliente desde una sesión verificada.
- Usar un checkpointer y almacenamiento persistentes para aprobaciones.
- Añadir pruebas automatizadas de API, RAG, clasificación y rutas de aprobación.
- Medir y calibrar umbrales con un conjunto de preguntas evaluado.
- Fijar y verificar versiones de dependencias en un entorno de CI.
- Definir límites de recursos y persistencia para despliegues de larga duración.
- Añadir observabilidad, métricas, políticas de retención y protección de datos.
