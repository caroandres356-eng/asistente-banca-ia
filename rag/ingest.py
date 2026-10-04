import shutil
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

DOCS = Path("data/docs")
DB = "chroma_db"
MODELO_EMB = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Reconstruimos el índice desde cero para no duplicar chunks al re-ejecutar
shutil.rmtree(DB, ignore_errors=True)

splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=60)

chunks = []
for archivo in sorted(DOCS.glob("*.txt")):
    texto = archivo.read_text(encoding="utf-8")
    for i, parte in enumerate(splitter.split_text(texto)):
        chunks.append(Document(page_content=parte,
                               metadata={"fuente": archivo.name, "chunk": i}))

emb = HuggingFaceEmbeddings(model_name=MODELO_EMB)
Chroma.from_documents(chunks, emb, persist_directory=DB)
print(f"Indexados {len(chunks)} chunks de {len(list(DOCS.glob('*.txt')))} documentos")