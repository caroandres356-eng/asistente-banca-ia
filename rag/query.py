import sys
from common import get_db

pregunta = " ".join(sys.argv[1:])
db = get_db()
for doc, dist in db.similarity_search_with_score(pregunta, k=3):
    print(f"[distancia {dist:.3f}] {doc.metadata['fuente']} (chunk {doc.metadata['chunk']})")
    print(doc.page_content[:200].replace("\n", " "), "\n")  