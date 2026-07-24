"""Vérifie l'état d'avancement de l'ingestion (lecture seule, non bloquant).

A lancer dans un autre terminal pendant que l'ingestion tourne :
  uv run bench/check_status.py [--total 299]
"""
import argparse

import duckdb

ap = argparse.ArgumentParser(description="État d'avancement de l'ingestion.")
ap.add_argument("--total", type=int, default=299, help="Nombre total de docs attendus.")
ap.add_argument("--db", default="knowledge.duckdb", help="Chemin de la base DuckDB.")
args = ap.parse_args()

con = duckdb.connect(args.db, read_only=True)
try:
    n_docs = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    # Table chunks : peut être absente sur une vieille base non migrée.
    try:
        n_chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_emb = con.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
        avg_len = con.execute("SELECT AVG(length(text)) FROM chunks").fetchone()[0] or 0
        chunks_ok = True
    except Exception:
        n_chunks = n_emb = 0
        avg_len = 0.0
        chunks_ok = False
    n_sum = con.execute(
        "SELECT COUNT(*) FROM document_ai_metadata "
        "WHERE summary NOT LIKE 'No summary%' AND summary != ''"
    ).fetchone()[0]

    print("=" * 50)
    print("  AVANCEMENT DE L'INGESTION")
    print("=" * 50)
    print(f"  Documents ingérés : {n_docs}/{args.total} ({100*n_docs//args.total}%)")
    if chunks_ok:
        print(f"  Chunks            : {n_chunks} ({n_emb} avec embedding)")
        print(f"  Taille moy. chunk : {avg_len:.0f} car")
    else:
        print("  Chunks            : table absente (base non migrée)")
    print(f"  Résumés LLM       : {n_sum}/{n_docs}")
    print(f"  Restant           : {args.total - n_docs} docs")
    print("=" * 50)
finally:
    con.close()
