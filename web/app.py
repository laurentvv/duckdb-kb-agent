from fastapi import FastAPI
from langsmith import traceable
import time
import logging

# Configure logging
logging.basicConfig(
    filename='rag_metrics.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RAG_Production")
from fastapi.responses import HTMLResponse, StreamingResponse
import json
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
from sentence_transformers import CrossEncoder

_cross_encoder = None

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', max_length=512)
    return _cross_encoder

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL")
client = OpenAI(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"), api_key="ollama")

class QueryRequest(BaseModel):
    question: str

class RAGResponse(BaseModel):
    answer: str
    source_url: list[str]
    page_number: list[int]
    confidence: float


@traceable(name='Retrieval & Reranking')
def get_context_from_db(query):
    """Recherche hybride au niveau chunk (FTS + vectoriel, fusion RRF).

    Privilégie la table chunks (granularité fine) ; repli sur la recherche au
    niveau document si la base n'a pas encore été migrée/re-remplie avec chunks.
    Renvoie (contexte_formaté, liste_sources, liste_chunks).
    """
    con = kb.connect(kb.DB_PATH, read_only=True)
    try:
        # Tentative chunk-level (recherche granulaire + métadonnées de structure).
        try:
            # Récupérer le top-50 pour le reranking
            chunks = kb.hybrid_search_chunks(con, query, k=50, mode="hybrid")
        except Exception:
            chunks = []
        if chunks:
            # Reranking avec Cross-Encoder
            pairs = [[query, c["text"]] for c in chunks]
            encoder = get_cross_encoder()
            scores = encoder.predict(pairs)
            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = scores[i]

            # Trier par score descendant et garder le top-10
            chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
            top_10 = chunks[:10]

            return _format_chunk_context(top_10), _chunk_sources(top_10), top_10

        # Repli document-level (ancienne base non migrée).
        results = kb.hybrid_search(con, query, k=2, mode="hybrid")
    finally:
        con.close()

    if not results:
        return "Aucun document trouvé.", [], []

    combined_context = ""
    sources = []
    for r in results:
        sources.append(r["file_name"])
        snippet = (r["raw_text"] or "")[:3000]
        combined_context += f"--- Document: {r['file_name']} ---\n{snippet}\n\n"
    return combined_context, sources, results


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

@traceable(name='Query Rewriting')
def rewrite_query(question: str) -> str:
    """Réécriture de la requête : Étendez les termes ambigus pour un meilleur rappel."""
    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "Tu es un expert en recherche documentaire. Ta tâche est de réécrire la question de l'utilisateur pour l'optimiser pour un moteur de recherche hybride (BM25 + vectoriel). Étends les termes ambigus, ajoute des synonymes pertinents et retourne UNIQUEMENT la requête réécrite, sans introduction ni explication."},
                {"role": "user", "content": f"Réécris cette question : {question}"}
            ],
            temperature=0.3,
            max_tokens=100
        )
        if not response.choices:
            return question
        rewritten = response.choices[0].message.content.strip()
        # Fallback if the LLM returns something too weird
        if not rewritten or len(rewritten) > 200:
            return question
        return rewritten
    except Exception as e:
        print(f"Error rewriting query: {e}")
        return question

@traceable(name='RAG Pipeline Execution')
async def execute_rag(question: str):
    start_time = time.time()

    # 1. Query Rewriting
    rewritten_query = rewrite_query(question)

    # 2. Retrieval & Reranking
    context, sources, chunks_data = get_context_from_db(rewritten_query)
    
    if not sources:
        logger.info(f"Retrieval failed for query: {question}")
        return None, "Je n'ai trouvé aucun document pertinent dans la base de connaissances pour cette question.", []

    logger.info(f"Retrieval success for query: {question} - sources: {len(sources)}")
    
    # 3. Prompting (JSON schema enforced)
    system_prompt = """Tu es un assistant IA spécialisé dans l'exploitation documentaire.
Citez les sources avec les numéros de page. Si incertain, dites 'Je ne sais pas'. Ne jamais inventer d'informations. Base-toi uniquement sur le contexte fourni.
Tu DOIS répondre au format JSON strict avec les clés suivantes :
- "answer": ta réponse formatée
- "source_url": liste des noms de fichiers ou chemins sources utilisés
- "page_number": liste des numéros de pages sources
- "confidence": un float entre 0.0 et 1.0 représentant ta confiance dans la réponse"""

    prompt = f"### Instruction \n Réponds à la question suivante : {question} \n\n ### Context \n {context} \n\n ### Answer (JSON only) \n"
    
    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        if not response.choices:
            raise ValueError("Empty choices returned from LLM")
        raw_content = response.choices[0].message.content
        latency = time.time() - start_time
        
        try:
            # Output validation with Pydantic
            validated_response = RAGResponse.model_validate_json(raw_content)
            
            # Confidence Threshold
            if validated_response.confidence < 0.7:
                logger.warning(f"Low confidence ({validated_response.confidence}) for query: {question}")
                final_answer = "J'ai besoin de plus de contexte pour répondre avec certitude."
                grounding_precision = 0.0
            else:
                final_answer = validated_response.answer
                grounding_precision = 1.0 # Simplified metric

            logger.info(f"Query processed. Latency: {latency:.2f}s, Confidence: {validated_response.confidence:.2f}, Grounding: {grounding_precision}")

            return validated_response, final_answer, sources

        except Exception as e:
            logger.error(f"Validation error: {e}, raw_content: {raw_content}")
            return None, "Erreur lors de la structuration de la réponse.", sources

    except Exception as e:
        logger.error(f"Generation error: {e}")
        return None, f"**Erreur**: {str(e)}", sources


@app.post("/api/ask")
async def ask_question(req: QueryRequest):
    # Wrapper pour adapter le JSON au stream attendu par le frontend
    validated, final_answer, sources = await execute_rag(req.question)

    async def mock_stream():
        yield f"data: {json.dumps({'sources': sources, 'chunk': final_answer})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(mock_stream(), media_type="text/event-stream")
