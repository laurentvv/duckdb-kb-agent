"""Benchmark RAG : pose 20 questions à plusieurs modèles LLM via Ollama.

Pipeline identique pour chaque modèle (équité) :
  Question -> FTS top-3 docs (raw_text) -> prompt RAG -> réponse -> strip thinking

Usage :
  uv run bench/run_bench.py
  uv run bench/run_bench.py --limit 3                 # test rapide (3 questions)
  uv run bench/run_bench.py --models lfm2.5:latest    # un seul modèle
"""

import argparse
import json
import re
import time
from pathlib import Path

import duckdb
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "knowledge.duckdb"
QUESTIONS = Path(__file__).parent / "questions.jsonl"
RESULTS_JSONL = Path(__file__).parent / "results.jsonl"
RESULTS_MD = Path(__file__).parent / "results.md"

OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODELS = [
    "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL",
    "lfm2.5:latest",
]
CTX_CHARS_PER_DOC = 2000     # caractères de raw_text par doc dans le contexte
CTX_MAX_TOTAL = 6000         # plafond total du contexte
TOP_K = 3                    # nb de docs remontés par la FTS


# -------------------------------------------------------------------- FTS / RAG

def search_context(query: str, db_path: Path = DB_PATH) -> tuple[str, list[str]]:
    """Retourne (contexte concaténé, liste des noms de docs sources) via FTS BM25."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        con.execute("LOAD fts;")
        # On répète l'expression BM25 dans le WHERE (alias non visible en SQL standard).
        rows = con.execute(
            f"""
            SELECT d.file_name, c.raw_text,
                   fts_main_document_content.match_bm25(c.document_id, ?) AS score
            FROM document_content c
            JOIN documents d ON c.document_id = d.id
            WHERE fts_main_document_content.match_bm25(c.document_id, ?) IS NOT NULL
            ORDER BY score DESC LIMIT {TOP_K}
            """,
            [query, query],
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return "(aucun document trouvé)", []

    context_parts, sources = [], []
    total = 0
    for name, raw_text, _score in rows:
        sources.append(name)
        snippet = (raw_text or "")[:CTX_CHARS_PER_DOC]
        if total + len(snippet) > CTX_MAX_TOTAL:
            snippet = snippet[: CTX_MAX_TOTAL - total]
        context_parts.append(f"--- Document : {name} ---\n{snippet}")
        total += len(snippet)
        if total >= CTX_MAX_TOTAL:
            break
    return "\n\n".join(context_parts), sources


def build_prompt(question: str, context: str) -> str:
    return f"""Tu es un assistant technique expert. Réponds à la question en te basant UNIQUEMENT sur le contexte fourni ci-dessous. Si la réponse ne s'y trouve pas, dis-le clairement. Sois précis et concis.

CONTEXTE :
{context}

QUESTION :
{question}
"""


# ------------------------------------------------------- Strip des balises thinking

# Gemma 4 : <|channel|>thought ... <|channel|>final (ou <channel|>)
_GEMMA_THINK = re.compile(
    r"<\|channel\|>\s*thought.*?(?=<\|channel\|>|$)", re.DOTALL | re.IGNORECASE
)
# LFM2.5 / qwen : <think> ... </think>
_LFM_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# Au cas où : retirer d'éventuels tokens spéciaux résiduels
_TOKEN_SCRUB = re.compile(r"<\|[^|]*\|>|<[^>]+>")


def strip_thinking(text: str) -> str:
    """Isole la réponse utile en supprimant les blocs de raisonnement."""
    if not text:
        return ""
    out = _GEMMA_THINK.sub("", text)
    out = _LFM_THINK.sub("", out)
    # Si après strip il ne reste qu'un préfixe de canal, on prend la fin
    # ex: "<|channel|>final\n..." -> on garde après le dernier canal
    if "<|channel|>" in out:
        parts = re.split(r"<\|channel\|>", out)
        out = parts[-1]
    out = out.strip()
    return out


# --------------------------------------------------------------------- Appel LLM

def ask_model(client, model: str, prompt: str, timeout: float = 180):
    """Appelle un modèle, renvoie (réponse_brute, temps_écoulé_s, tokens)."""
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            timeout=timeout,
        )
        elapsed = time.time() - t0
        raw = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        tokens = getattr(usage, "completion_tokens", None) if usage else None
        return raw, elapsed, tokens
    except Exception as e:
        return f"[ERREUR: {e}]", time.time() - t0, None


def warmup(client, model: str):
    """Un appel factice pour charger le modèle en mémoire (évite le biais à froid)."""
    try:
        ask_model(client, model, "Réponds juste : OK", timeout=300)
    except Exception:
        pass


# ------------------------------------------------------------------------ Main

def main():
    ap = argparse.ArgumentParser(description="Benchmark RAG multi-modèles.")
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS, help="Modèles à tester.")
    ap.add_argument("--limit", type=int, help="Limiter aux N premières questions (test rapide).")
    args = ap.parse_args()

    questions = []
    with open(QUESTIONS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    if args.limit:
        questions = questions[: args.limit]

    print(f"Benchmark : {len(questions)} questions × {len(args.models)} modèle(s).")
    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

    # Préchauffage de chaque modèle.
    for m in args.models:
        print(f"  Préchauffe {m} ...", flush=True)
        warmup(client, m)

    runs = []
    total = len(questions) * len(args.models)
    done = 0
    for q in questions:
        context, sources = search_context(q["question"])
        prompt = build_prompt(q["question"], context)
        for model in args.models:
            done += 1
            print(f"[{done}/{total}] Q{q['id']:>2} × {model.split('/')[-1][:30]}", flush=True)
            raw, elapsed, tokens = ask_model(client, model, prompt)
            answer = strip_thinking(raw)
            runs.append({
                "id": q["id"],
                "question": q["question"],
                "theme": q.get("theme", ""),
                "expected_doc_hint": q.get("expected_doc_hint", ""),
                "context_sources": sources,
                "model": model,
                "answer_raw": raw,
                "answer": answer,
                "elapsed_s": round(elapsed, 1),
                "tokens": tokens,
            })

    # --- Écriture results.jsonl
    with open(RESULTS_JSONL, "w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # --- Écriture results.md
    lines = ["# Résultats du benchmark\n",
             f"{len(questions)} questions × {len(args.models)} modèle(s).\n",
             "| Q | Thème | Modèle | Latence (s) | Réponse (extrait) |",
             "|---|---|---|---|---|"]
    for r in runs:
        excerpt = r["answer"].replace("|", "/").replace("\n", " ")[:180]
        mshort = r["model"].split("/")[-1]
        lines.append(f'| {r["id"]} | {r["theme"]} | {mshort} | {r["elapsed_s"]} | {excerpt} |')
    with open(RESULTS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nTerminé : {RESULTS_JSONL}")
    print(f"         {RESULTS_MD}")


if __name__ == "__main__":
    main()
