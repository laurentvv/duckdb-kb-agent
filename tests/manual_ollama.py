"""Utilitaire d'intégration manuel : interroge la base + Ollama (non pytest).

À exécuter à la main pour valider la chaîne complète (DuckDB FTS -> LLM) :

    uv run python tests/manual_ollama.py "votre question technique"

Nécessite :
  - knowledge.duckdb présent et indexé
  - Ollama démarré avec le modèle Gemma 4
"""

import os
import sys
from pathlib import Path

# Lib partagée (cwd = racine du projet à l'exécution)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kb
from openai import OpenAI

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL")
client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


def get_context_from_db(query):
    con = kb.connect("knowledge.duckdb", read_only=True)
    try:
        results = kb.hybrid_search_chunks(con, query, k=5, mode="hybrid")
        if not results:
            return ""
            
        xml_context = ""
        for i, r in enumerate(results, start=1):
            source = f"{r['file_name']} - Page {r['page_number']}" if r.get('page_number') else r['file_name']
            xml_context += f'<document index="{i}">\n  <source>{source}</source>\n  <content>{r["text"]}</content>\n</document>\n\n'
        return xml_context
    finally:
        con.close()


def ask_ollama(question, context):
    system_prompt = "Answer only from the document context below. Do not fall back to your general knowledge. If they do not contain enough information, reply that you do not have the information needed to answer and name what is missing. Never invent information. Ground your answer strictly in these documents and cite their sources."
    
    prompt = f"### Instruction \n {question} \n\n ### Context \n {context} \n\n ### Answer \n"
    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
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
    if not context:
        print("> Aucun document trouvé.")
    else:
        print("> Appel du LLM...")
        answer = ask_ollama(q, context)
        print(f"\n=> RÉPONSE :\n{answer}\n")
