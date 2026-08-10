from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import json
import uuid
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
# pylint: disable=duplicate-code
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


def rewrite_query(question: str) -> str:
    """
    Réécrit la requête utilisateur pour améliorer la recherche sémantique RAG.
    """
    prompt = f"""Rewrite the following user question to make it optimal for a keyword and semantic search in a knowledge base.
    Fix any typos, expand abbreviations if obvious, and add relevant synonyms.
    Keep the query concise and focused on the core information needed.
    DO NOT answer the question. ONLY output the rewritten query.

    Original question: {question}

    Rewritten query:"""

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50
        )
        rewritten = response.choices[0].message.content.strip()
        print(f"Original query: '{question}' -> Rewritten: '{rewritten}'")
        # En cas de problème où le modèle bavarde trop, on nettoie un peu
        if rewritten.lower().startswith("rewritten query:"):
            rewritten = rewritten[len("rewritten query:"):].strip()
        return rewritten if rewritten else question
    except Exception as e:
        print(f"Error rewriting query: {e}")
        return question

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
    """Formate les chunks en contexte XML pour le LLM (anti-hallucination)."""
    parts = []
    for i, c in enumerate(chunks, start=1):
        source = f"{c['file_name']} - Page {c['page_number']}" if c.get('page_number') else c.get('file_name', 'Source Inconnue')
        parts.append(f'<document index="{i}">\n  <source>{source}</source>\n  <content>{c["text"]}</content>\n</document>\n')
    return "\n".join(parts)


def _chunk_sources(chunks: list[dict]) -> list[str]:
    """Liste des noms de documents sources (dédoublonnés) avec numéro de page et section."""
    seen = []
    for c in chunks:
        name = c.get("file_name")
        if not name:
            continue
        
        parts = [name]
        if c.get("page_number"):
            parts.append(f"p.{c['page_number']}")
        if c.get("section"):
            parts.append(c["section"])
            
        label = " - ".join(parts)
        if label not in seen:
            seen.append(label)
    return seen

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("web/static/index.html", "r", encoding="utf-8") as f:
        return f.read()


class FeedbackRequest(BaseModel):
    interaction_id: str
    rating: str
    comment: str = ""

@app.post("/api/feedback")
async def receive_feedback(req: FeedbackRequest):
    con = kb.connect(kb.DB_PATH, read_only=False)
    try:
        con.execute(
            "UPDATE feedbacks SET rating = ?, comment = ? WHERE id = ?",
            [req.rating, req.comment, req.interaction_id]
        )
    finally:
        con.close()
    return {"status": "ok"}

@app.post("/api/ask")
async def ask_question(req: QueryRequest):
    question = req.question

    # ÉTAPE 1 : Réécriture de la requête
    rewritten_query = rewrite_query(question)

    context, sources = get_context_from_db(rewritten_query)

    interaction_id = str(uuid.uuid4())
    
    if not sources:
        async def mock_stream():
            answer = "Je n'ai trouvé aucun document pertinent dans la base de connaissances pour cette question."

            # Stocker en base (feedback empty)
            con = kb.connect(kb.DB_PATH, read_only=False)
            try:
                con.execute(
                    "INSERT INTO feedbacks (id, question, rewritten_query, context, answer) VALUES (?, ?, ?, ?, ?)",
                    [interaction_id, question, rewritten_query, "", answer]
                )
            except Exception as e:
                print(f"Error saving to feedbacks: {e}")
            finally:
                con.close()

            msg = json.dumps({'interaction_id': interaction_id, 'sources': [], 'chunk': answer})
            yield f"data: {msg}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(mock_stream(), media_type="text/event-stream")
    
    system_prompt = "Answer only from the document context below. Do not fall back to your general knowledge. If they do not contain enough information, reply that you do not have the information needed to answer and name what is missing. Never invent information. Ground your answer strictly in these documents and cite their sources."
    prompt = f"### Instruction \n {question} \n\n ### Context \n {context} \n\n ### Answer \n"
    
    async def generate():
        # Envoie immédiat des sources et interaction_id
        yield f"data: {json.dumps({'interaction_id': interaction_id, 'sources': sources, 'chunk': ''})}\n\n"
        
        full_answer = ""
        try:
            response = client.chat.completions.create(
              model=OLLAMA_MODEL,
              messages=[
                  {"role": "system", "content": system_prompt},
                  {"role": "user", "content": prompt}
              ],
              temperature=0.1,
              stream=True
            )
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_answer += delta
                    yield f"data: {json.dumps({'chunk': delta})}\n\n"

            # Stocker en base une fois terminé
            con = kb.connect(kb.DB_PATH, read_only=False)
            try:
                con.execute(
                    "INSERT INTO feedbacks (id, question, rewritten_query, context, answer) VALUES (?, ?, ?, ?, ?)",
                    [interaction_id, question, rewritten_query, context, full_answer]
                )
            except Exception as e:
                print(f"Error saving to feedbacks: {e}")
            finally:
                con.close()

            yield "data: [DONE]\n\n"
        except Exception as e:
            error_msg = f"\n\n**Erreur**: {str(e)}"
            yield f"data: {json.dumps({'chunk': error_msg})}\n\n"
            yield "data: [DONE]\n\n"
            
    return StreamingResponse(generate(), media_type="text/event-stream")
