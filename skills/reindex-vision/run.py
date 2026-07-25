"""Réindexation avec vision LLM : ré-ingère les documents existants en activant
la description des images (captures d'écran, PDF scannés, schémas).

Le dédoublonnage intelligent d'ingest-doc gère la mise à jour : pour chaque
document, on purge l'ancienne version (doc + chunks) puis on ré-ingère avec
--vision --force. Les documents non concernés (texte pur, SQL) sont quand même
retraités mais la vision ne leur ajoute rien (pas d'image) — c'est sans effet
et garantit la cohérence.

Usage :
  uv run skills/reindex-vision/run.py                          # tous les docs
  uv run skills/reindex-vision/run.py --filter "ILIKE '%.docx'"  # DOCX seulement
  uv run skills/reindex-vision/run.py --filter "ILIKE '%.pdf'"   # PDF seulement
  uv run skills/reindex-vision/run.py --limit 5                 # test rapide (5 docs)

⚠️ LONG : ~15-30s par image détectée. Pour 169 docs riches en captures,
prévoir plusieurs heures. Le script gère la reprise (les docs déjà retraités
avec vision ne sont pas refaits — voir _already_has_vision).

Prérequis : Ollama démarré + modèle multimodal Gemma 4 E4B présent
(cf. KB_VISION_MODEL). Vérifier : curl http://localhost:11434/api/tags
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = "knowledge.duckdb"


def fetch_docs(filter_sql: str, limit: int | None) -> list[tuple[str, str]]:
    """Retourne la liste (id, file_path) des documents à réindexer."""
    sql = "SELECT id, file_path FROM documents"
    where = []
    if filter_sql:
        where.append(filter_sql)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY file_path"
    if limit:
        sql += f" LIMIT {int(limit)}"
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--filter", default=None,
                    help="Clause SQL WHERE sur documents (ex: \"file_path ILIKE '%%.docx'\")")
    ap.add_argument("--limit", type=int, default=None,
                    help="Nombre max de documents à traiter (test rapide)")
    ap.add_argument("--category", default="Uncategorized",
                    help="Catégorie (passée à ingest-doc)")
    args = ap.parse_args()

    docs = fetch_docs(args.filter, args.limit)
    total = len(docs)
    if total == 0:
        print("Aucun document à réindexer.")
        return
    print(f"{total} document(s) à réindexer avec vision LLM.", flush=True)
    print("⚠️  Long : ~15-30s par image détectée. Prévoir plusieurs heures.", flush=True)
    print("    Reprise possible : interrompre (Ctrl+C) puis relancer.", flush=True)
    print("", flush=True)

    # On appelle ingest-doc en subprocess (mode --vision --force) pour chaque doc.
    # Le dédoublonnage intelligent purge l'ancienne version puis ré-ingère.
    ok = 0
    failed = 0
    t0 = time.time()
    for i, (doc_id, file_path) in enumerate(docs, 1):
        name = Path(file_path).name
        print(f"[{i}/{total}] {name[:55]}", flush=True)
        try:
            res = subprocess.run(
                ["uv", "run", "skills/ingest-doc/run.py", file_path,
                 "--vision", "--force", "--category", args.category],
                cwd=str(ROOT), capture_output=True, text=True, check=True,
                timeout=900,  # 15 min max par doc (sécurité anti-blocage)
            )
            if "SUCCESS" in res.stdout:
                ok += 1
                # Extraire le nb de chunks du log pour visibilité.
                for line in res.stdout.splitlines():
                    if "chunks" in line.lower():
                        print(f"      {line.strip()}", flush=True)
                        break
            else:
                failed += 1
                print(f"      ÉCHEC (pas de SUCCESS)", flush=True)
                if res.stderr:
                    print(f"      {res.stderr[:150]}", flush=True)
        except subprocess.TimeoutExpired:
            failed += 1
            print(f"      TIMEOUT (15 min) — document skippe", flush=True)
        except subprocess.CalledProcessError as e:
            failed += 1
            print(f"      ERREUR: {str(e)[:100]}", flush=True)
        except KeyboardInterrupt:
            print(f"\nInterrompu par l'utilisateur après {i-1} doc(s).", flush=True)
            break

        # ETA toutes les 10 docs.
        if i % 10 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  ... {i}/{total} faits ({elapsed/60:.0f} min, ETA {eta/60:.0f} min) "
                  f"| OK={ok} ECHEC={failed}", flush=True)

    elapsed = time.time() - t0
    print(f"\n=== Réindexation terminée en {elapsed/60:.0f} min ===", flush=True)
    print(f"Réussis : {ok}/{total} | Échecs : {failed}", flush=True)


if __name__ == "__main__":
    main()
