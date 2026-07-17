"""Utilitaire d'intégration manuel : interroge la base + Ollama (non pytest).

À exécuter à la main pour valider la chaîne complète (DuckDB FTS -> LLM) :

    uv run python tests/manual_ollama.py "votre question technique"

Nécessite :
  - knowledge.duckdb présent et indexé
  - Ollama démarré avec le modèle Gemma 4
"""

import os
import sys

import duckdb
from openai import OpenAI

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL")
client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


def get_context_from_db(query):
    con = duckdb.connect("knowledge.duckdb", read_only=True)
    try:
        con.execute("LOAD fts;")
        # L'expression BM25 est répétée dans le WHERE (l'alias du SELECT n'y est
        # pas visible en SQL standard).
        res = con.execute(
            """
            SELECT d.file_path, dc.raw_text,
                   fts_main_document_content.match_bm25(dc.document_id, ?) AS score
            FROM document_content dc
            JOIN documents d ON dc.document_id = d.id
            WHERE fts_main_document_content.match_bm25(dc.document_id, ?) IS NOT NULL
            ORDER BY score DESC
            LIMIT 2
            """,
            [query, query],
        ).fetchall()

        if res:
            combined_context = ""
            for r in res:
                combined_context += f"--- Document: {r[0]} ---\n{r[1][:3000]}\n\n"
            return combined_context
        return "Aucun document trouvé."
    finally:
        con.close()


def ask_ollama(question, context):
    prompt = f"""Tu es un assistant technique expert. Voici un extrait de la base documentaire technique. Rédige une procédure claire étape par étape en utilisant UNIQUEMENT ce contexte.

CONTEXTE RETOURNÉ PAR LA BDD :
{context}

QUESTION :
{question}
"""
    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur: {e}"


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "création portail web"
    print(f"Modèle Ollama : {OLLAMA_MODEL}\n")
    print(f"Question : {q}")
    print("> Recherche dans DuckDB...")
    context = get_context_from_db(q)
    print("> Appel du LLM...")
    answer = ask_ollama(q, context)
    print(f"\n=> RÉPONSE :\n{answer}\n")
