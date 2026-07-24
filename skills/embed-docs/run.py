"""Remplit la colonne document_content.embedding (bge-m3 via Ollama).

À lancer une fois après l'initialisation, puis après chaque ingestion massive.
Reprise sécurisée : ne traite que les docs sans embedding (embedding IS NULL).

Usage :
  uv run skills/embed-docs/run.py                               # tous les docs manquants
  uv run skills/embed-docs/run.py --filter "file_path ILIKE '%\\sage\\%'"   # seulement le dossier Sage
  uv run skills/embed-docs/run.py --limit 5                     # test rapide
  uv run skills/embed-docs/run.py --rebuild                     # force le recalcul de tout
"""

import argparse
import sys
from pathlib import Path

# Import de la lib partagée (cwd = racine du projet à l'exécution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import kb  # noqa: E402


def fetch_pending(con, rebuild: bool, filter_sql: str, limit: int | None):
    """Retourne la liste des (document_id, raw_text) à embedder."""
    where_parts = ["length(coalesce(c.raw_text, '')) > 0"]  # ignore les textes vides
    if not rebuild:
        where_parts.append("c.embedding IS NULL")
    where = " AND ".join(where_parts)
    sql = f"""
        SELECT c.document_id, c.raw_text
        FROM document_content c JOIN documents d ON c.document_id = d.id
        WHERE {where}
    """
    if filter_sql:
        sql += f" AND ({filter_sql})"
    sql += " ORDER BY c.document_id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql).fetchall()


def rebuild_hnsw(con):
    """DROP + recréer l'index HNSW (le build incrémental est capricieux)."""
    try:
        con.execute("DROP INDEX IF EXISTS idx_content_embedding;")
        con.execute(
            "CREATE INDEX idx_content_embedding "
            "ON document_content USING HNSW (embedding) WITH (metric = 'cosine');"
        )
        print("Index HNSW reconstruit.")
    except Exception as e:
        print(f"Warning: rebuild HNSW échoué (ignoré) : {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--filter", default=None,
                    help="Clause SQL WHERE additionnelle (ex: \"file_path ILIKE '%%\\sage\\%%'\")")
    ap.add_argument("--limit", type=int, default=None, help="Nombre max de docs à traiter")
    ap.add_argument("--rebuild", action="store_true", help="Recalculer tous les embeddings")
    ap.add_argument("--model", default=kb.EMBED_MODEL, help=f"Modèle embedding (défaut: {kb.EMBED_MODEL})")
    ap.add_argument("--db", default=kb.DB_PATH, help="Chemin de la base DuckDB")
    args = ap.parse_args()

    con = kb.connect(args.db)
    try:
        pending = fetch_pending(con, args.rebuild, args.filter, args.limit)
        total = len(pending)
        if total == 0:
            print("Aucun document à embedder (tous ont déjà un embedding).")
            return
        print(f"{total} document(s) à embedder avec {args.model}.\n")

        # L'index HNSW ne supporte pas les UPDATE incrémentaux (duplicate keys).
        # On le droppe pendant la boucle, on le reconstruit à la fin.
        con.execute("DROP INDEX IF EXISTS idx_content_embedding;")

        done = 0
        failed = 0
        for i, (doc_id, raw_text) in enumerate(pending, 1):
            text = kb.truncate(raw_text)
            # Retry léger : 2 tentatives pour absorber les surcharges transitoires d'Ollama.
            vec = None
            for attempt in range(2):
                vec = kb.embed(text, model=args.model)
                if vec is not None:
                    break
            if vec is None:
                print(f"  [{i}/{total}] ECHEC embedding (Ollama down ?) -> {doc_id[:12]}... (skip)")
                failed += 1
                continue
            con.execute(
                "UPDATE document_content SET embedding = ? WHERE document_id = ?",
                [vec, doc_id],
            )
            done += 1
            if i % 5 == 0 or i == total:
                print(f"  [{i}/{total}] {done} embeddés.", flush=True)

        print(f"\nTerminé : {done}/{total} embeddings calculés ({failed} échec(s)).")
        # Reconstruire l'index HNSW une fois la masse écrite.
        rebuild_hnsw(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
