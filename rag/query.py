import sys
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

MODELO_EMB = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
pregunta = " ".join(sys.argv[1:])

emb = HuggingFaceEmbeddings(model_name=MODELO_EMB)
db = Chroma(persist_directory="chroma_db", embedding_function=emb)

for doc, distancia in db.similarity_search_with_score(pregunta, k=3):
    print(f"[distancia {distancia:.3f}] {doc.metadata['fuente']} (chunk {doc.metadata['chunk']})")
    print(doc.page_content[:200].replace("\n", " "), "\n")