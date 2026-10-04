from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

MODELO_EMB = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DB = "chroma_db"

def get_emb():
    return HuggingFaceEmbeddings(model_name=MODELO_EMB)

def get_db():
    return Chroma(persist_directory=DB, embedding_function=get_emb())