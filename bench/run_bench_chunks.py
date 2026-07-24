"""Benchmark RAG niveau CHUNKS : pose les 20 questions à un modèle via Ollama.

Pipeline (identique à run_bench.py sauf le retrieval qui passe au niveau chunk) :
  Question -> hybrid_search_chunks (FTS + vectoriel + RRF) -> top-k chunks
           -> contexte (texte complet des chunks + citations page/section)
           -> prompt RAG -> réponse -> strip thinking

Comparaison directe et équitable avec run_bench.py (baseline FTS document-level) :
  - mêmes 20 questions (questions.jsonl)
  - même modèle, même prompt, même température
  - SEUL le retrieval change (chunks vs documents)

Usage :
  uv run bench/run_bench_chunks.py
  uv run bench/run_bench_chunks.py --limit 5                    # test rapide
  uv run bench/run_bench_chunks.py --models lfm2.5:latest       # autre modèle
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kb  # noqa: E402

QUESTIONS = Path(__file__).parent / "questions.jsonl"
RESULTS_JSONL = Path(__file__).parent / "results_chunks.jsonl"
RESULTS_MD = Path(__file__).parent / "results_chunks.md"

OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODELS = [
    "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL",
]
TOP_K_CHUNKS = 5                # nb de chunks remontés par la recherche hybride
MAX_CHUNKS_PER_DOC = 2          # diversification des sources (max 2 chunks/doc)
CTX_MAX_TOTAL = 6000            # plafond total du contexte (caractères)


# -------------------------------------------------------------------- Retrieval

def search_context(query: str) -> tuple[str, list[str]]:
    """Recherche hybride niveau chunk -> contexte + sources."""
    con = kb.connect(kb.DB_PATH, read_only=True)
    try:
        try:
            chunks = kb.hybrid_search_chunks(
                con, query, k=TOP_K_CHUNKS, mode="hybrid",
                max_chunks_per_doc=MAX_CHUNKS_PER_DOC,
            )
        except Exception:
            chunks = []
        if not chunks:
            # Repli document-level si la base n'a pas de chunks.
            results = kb.hybrid_search(con, query, k=3, mode="hybrid")
            context_parts, sources = [], []
            total = 0
            for r in results:
                sources.append(r["file_name"])
                snippet = (r["raw_text"] or "")[:2000]
                if total + len(snippet) > CTX_MAX_TOTAL:
                    snippet = snippet[: CTX_MAX_TOTAL - total]
                context_parts.append(f"--- Document : {r['file_name']} ---\n{snippet}")
                total += len(snippet)
                if total >= CTX_MAX_TOTAL:
                    break
            return "\n\n".join(context_parts), sources
    finally:
        con.close()

    # Formatage contexte chunk-level avec citations (page/section/type).
    context_parts, sources = [], []
    seen_docs = []
    total = 0
    for c in chunks:
        cite = []
        if c.get("section"):
            cite.append(c["section"])
        if c.get("page_number"):
            cite.append(f"p.{c['page_number']}")
        cite_str = f" ({', '.join(cite)})" if cite else ""
        chunk_text = c["text"] or ""
        if total + len(chunk_text) > CTX_MAX_TOTAL:
            chunk_text = chunk_text[: CTX_MAX_TOTAL - total]
        context_parts.append(
            f"--- {c['file_name']} — {c.get('element_type','Texte')}{cite_str} ---\n{chunk_text}"
        )
        total += len(chunk_text)
        if c["file_name"] not in seen_docs:
            seen_docs.append(c["file_name"])
        if total >= CTX_MAX_TOTAL:
            break
    return "\n\n".join(context_parts), seen_docs


def build_prompt(question: str, context: str) -> str:
    return f"""Tu es un assistant technique expert. Réponds à la question en te basant UNIQUEMENT sur le contexte fourni ci-dessous. Si la réponse ne s'y trouve pas, dis-le clairement. Sois précis et concis.

CONTEXTE :
{context}

QUESTION :
{question}
"""


# ------------------------------------------------------- Strip des balises thinking

_GEMMA_THINK = re.compile(
    r"<\|channel\|>\s*thought.*?(?=<\|channel\|>|$)", re.DOTALL | re.IGNORECASE
)
_LFM_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TOKEN_SCRUB = re.compile(r"<\|[^|]*\|>|<[^>]+>")


def strip_thinking(text: str) -> str:
    if not text:
        return ""
    out = _GEMMA_THINK.sub("", text)
    out = _LFM_THINK.sub("", out)
    if "<|channel|>" in out:
        parts = re.split(r"<\|channel\|>", out)
        out = parts[-1]
    out = out.strip()
    return out


# --------------------------------------------------------------------- Appel LLM

def ask_model(client, model: str, prompt: str, timeout: float = 180):
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
    try:
        ask_model(client, model, "Réponds juste : OK", timeout=300)
    except Exception:
        pass


# ------------------------------------------------------------------------ Main

def main():
    ap = argparse.ArgumentParser(description="Benchmark RAG niveau chunks.")
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

    print(f"Benchmark CHUNKS : {len(questions)} questions × {len(args.models)} modèle(s).")
    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

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

    with open(RESULTS_JSONL, "w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lines = ["# Résultats du benchmark (niveau chunks)\n",
             f"{len(questions)} questions × {len(args.models)} modèle(s).\n",
             "| Q | Thème | Modèle | Latence (s) | Sources | Réponse (extrait) |",
             "|---|---|---|---|---|---|"]
    for r in runs:
        excerpt = r["answer"].replace("|", "/").replace("\n", " ")[:150]
        mshort = r["model"].split("/")[-1]
        srcs = ", ".join(Path(s).name[:25] for s in r["context_sources"][:2])
        lines.append(f'| {r["id"]} | {r["theme"]} | {mshort} | {r["elapsed_s"]} | {srcs} | {excerpt} |')
    with open(RESULTS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nTerminé : {RESULTS_JSONL}")
    print(f"         {RESULTS_MD}")


if __name__ == "__main__":
    main()
