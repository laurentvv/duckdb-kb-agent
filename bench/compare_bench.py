"""Compare les résultats du benchmark baseline (FTS document) vs chunks.

Lit bench/results.jsonl (baseline) et bench/results_chunks.jsonl (nouveau),
produit un tableau comparatif par question : sources retrouvées, latence,
extrait de réponse.

Usage :
  uv run bench/compare_bench.py
"""

import json
from pathlib import Path

BENCH = Path(__file__).parent
BASELINE = BENCH / "results.jsonl"
CHUNKS = BENCH / "results_chunks.jsonl"
EXPECTED = BENCH / "expected_answers.md"


def load(path):
    out = []
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    base = load(BASELINE)
    chunks = load(CHUNKS)

    if not chunks:
        print("Aucun résultat chunks trouvé (bench/run_bench_chunks.py pas encore lancé ?).")
        return
    if not base:
        print("Aucun résultat baseline trouvé (bench/results.jsonl).")

    print("=" * 80)
    print("COMPARAISON BASELINE (FTS document) vs CHUNKS (hybride chunk-level)")
    print("=" * 80)

    # Indexer par id (on ne compare que le 1er modèle de chaque).
    base_by_id = {}
    for r in base:
        if r["id"] not in base_by_id:
            base_by_id[r["id"]] = r
    chunks_by_id = {r["id"]: r for r in chunks}

    print(f"\n{'Q':>3} | {'Sources BASE':<35} | {'Sources CHUNKS':<35} | {'Lat B':>5} | {'Lat C':>5}")
    print("-" * 95)

    same_sources = 0
    base_latency = []
    chunk_latency = []
    for qid in sorted(chunks_by_id.keys()):
        cb = base_by_id.get(qid, {})
        cc = chunks_by_id[qid]
        src_b = ", ".join(Path(s).name[:16] for s in cb.get("context_sources", [])[:2])
        src_c = ", ".join(Path(s).name[:16] for s in cc.get("context_sources", [])[:2])
        lat_b = cb.get("elapsed_s", "-")
        lat_c = cc.get("elapsed_s", "-")
        if isinstance(lat_b, (int, float)):
            base_latency.append(lat_b)
        if isinstance(lat_c, (int, float)):
            chunk_latency.append(lat_c)
        if cb.get("context_sources") == cc.get("context_sources") and cb.get("context_sources"):
            same_sources += 1
        print(f"{qid:>3} | {src_b:<35} | {src_c:<35} | {str(lat_b):>5} | {str(lat_c):>5}")

    print("-" * 95)
    print(f"\nSources identiques: {same_sources}/{len(chunks_by_id)}")
    if base_latency and chunk_latency:
        avg_b = sum(base_latency) / len(base_latency)
        avg_c = sum(chunk_latency) / len(chunk_latency)
        print(f"Latence moyenne  - baseline: {avg_b:.1f}s | chunks: {avg_c:.1f}s "
              f"({(avg_c-avg_b)/avg_b*100:+.0f}%)")

    # Détail des réponses : questions où les sources diffèrent (potentiel gain).
    print("\n" + "=" * 80)
    print("QUESTIONS OÙ LES SOURCES DIFFÈRENT (potentiel gain du chunking)")
    print("=" * 80)
    for qid in sorted(chunks_by_id.keys()):
        cb = base_by_id.get(qid, {})
        cc = chunks_by_id[qid]
        if cb.get("context_sources") != cc.get("context_sources"):
            q_text = cc["question"][:70]
            print(f"\nQ{qid}: {q_text}")
            print(f"  BASE  : {cb.get('context_sources', [])}")
            print(f"  CHUNKS: {cc.get('context_sources', [])}")


if __name__ == "__main__":
    main()
