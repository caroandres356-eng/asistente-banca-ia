import shutil
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from common import get_emb, DB

DOCS = Path("data/docs")
shutil.rmtree(DB, ignore_errors=True)

splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=60)
chunks = []
for archivo in sorted(DOCS.glob("*.txt")):
    texto = archivo.read_text(encoding="utf-8")
    for i, parte in enumerate(splitter.split_text(texto)):
        chunks.append(Document(page_content=parte,
                               metadata={"fuente": archivo.name, "chunk": i}))

Chroma.from_documents(chunks, get_emb(), persist_directory=DB)
print(f"Indexados {len(chunks)} chunks de {len(list(DOCS.glob('*.txt')))} documentos")