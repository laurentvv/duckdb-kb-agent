from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
import os
import sys
from pathlib import Path

# Lib partagée kb (recherche hybride)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kb

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL")
client = OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), api_key="ollama")

class QueryRequest(BaseModel):
    question: str

def get_context_from_db(query):
    """Recherche hybride au niveau chunk (FTS + vectoriel, fusion RRF).

    Privilégie la table chunks (granularité fine) ; repli sur la recherche au
    niveau document si la base n'a pas encore été migrée/re-remplie avec chunks.
    Renvoie (contexte_formaté, liste_sources).
    """
    con = kb.connect(kb.DB_PATH, read_only=True)
    try:
        # Tentative chunk-level (recherche granulaire + métadonnées de structure).
        try:
            chunks = kb.hybrid_search_chunks(con, query, k=5, mode="hybrid")
        except Exception:
            chunks = []
        if chunks:
            return _format_chunk_context(chunks), _chunk_sources(chunks)
        # Repli document-level (ancienne base non migrée).
        results = kb.hybrid_search(con, query, k=2, mode="hybrid")
    finally:
        con.close()

    if not results:
        return "Aucun document trouvé.", []

    combined_context = ""
    sources = []
    for r in results:
        sources.append(r["file_name"])
        snippet = (r["raw_text"] or "")[:3000]
        combined_context += f"--- Document: {r['file_name']} ---\n{snippet}\n\n"
    return combined_context, sources


def _format_chunk_context(chunks: list[dict]) -> str:
    """Formate les chunks en contexte pour le LLM, avec citations (page/section).

    Le résumé prépendu est celui du document du chunk top-1 (le plus pertinent),
    étiqueté avec son nom de fichier — et non un summary générique qui pourrait
    appartenir à un document différent dans un résultat multi-docs.
    """
    parts = []
    if chunks:
        top = chunks[0]
        summary = top.get("summary")
        if summary and not str(summary).startswith("No summary"):
            parts.append(f"[Résumé de {top.get('file_name', 'document')}] {summary}\n")
    for c in chunks:
        cite = []
        if c.get("section"):
            cite.append(f"section: {c['section']}")
        if c.get("page_number") is not None:
            cite.append(f"page {c['page_number']}")
        cite_str = f" ({', '.join(cite)})" if cite else ""
        header = f"--- {c['file_name']} — {c.get('element_type', 'Texte')}{cite_str} ---"
        parts.append(f"{header}\n{c['text']}\n")
    return "\n".join(parts)


def _chunk_sources(chunks: list[dict]) -> list[str]:
    """Liste des noms de documents sources (dédoublonnés, ordre de pertinence)."""
    seen = []
    for c in chunks:
        name = c.get("file_name")
        if name and name not in seen:
            seen.append(name)
    return seen

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("web/static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/ask")
async def ask_question(req: QueryRequest):
    question = req.question
    context, sources = get_context_from_db(question)
    
    if not sources:
        return {"answer": "Je n'ai trouvé aucun document pertinent dans la base de connaissances pour cette question.", "sources": []}
    
    prompt = f"""Tu es un assistant technique expert. Utilise UNIQUEMENT le contexte ci-dessous pour répondre à la question de manière précise et structurée. Ne mentionne pas que tu es une IA.
    
CONTEXTE :
{context}

QUESTION :
{question}
"""
    try:
        response = client.chat.completions.create(
          model=OLLAMA_MODEL,
          messages=[{"role": "user", "content": prompt}],
          temperature=0.1
        )
        answer = response.choices[0].message.content
        return {"answer": answer, "sources": sources}
    except Exception as e:
        return {"answer": f"Erreur lors de la génération avec Ollama: {str(e)}", "sources": []}
