"""Réindexation avec vision LLM : ré-ingère les documents existants en activant
la description des images (captures d'écran, PDF scannés, schémas).

Pour chaque document, on appelle ``ingest-doc --vision --force`` : le
dédoublonnage intelligent purge l'ancienne version (doc + chunks) puis
ré-ingère la nouvelle avec les descriptions d'images. Les documents sans image
(texte pur, SQL) sont retraités sans gain (la vision n'ajoute rien) — c'est
inoffensif et garantit la cohérence.

⚠️ ``--force`` contourne le dédoublonnage par hash, donc SUIVI EXPLICITE de la
progression pour permettre la reprise : un fichier ``.reindex-vision-done.json``
à côté de la base enregistre les ``doc_id`` déjà retraités avec succès. En cas
d'interruption (Ctrl+C), relancer le script reprend là où il s'est arrêté.

Usage :
  uv run skills/reindex-vision/run.py                          # tous les docs
  uv run skills/reindex-vision/run.py --filter "ILIKE '%.docx'"  # DOCX seulement
  uv run skills/reindex-vision/run.py --filter "ILIKE '%.pdf'"   # PDF seulement
  uv run skills/reindex-vision/run.py --limit 5                 # test rapide (5 docs)
  uv run skills/reindex-vision/run.py --reset                   # repart de zéro

⚠️ LONG : ~15-30s par image détectée. Pour 169 docs riches en captures,
prévoir plusieurs heures.

Prérequis : Ollama démarré + modèle multimodal Gemma 4 E4B présent
(cf. KB_VISION_MODEL). Vérifier : curl http://localhost:11434/api/tags
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import duckdb

# Chemin absolu : robuste quel que soit le cwd au lancement.
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT / "knowledge.duckdb")
# Sidecar de progression : liste des doc_id déjà retraités avec succès (reprise).
PROGRESS_FILE = str(ROOT / "knowledge.reindex-vision-done.json")


def load_done() -> set[str]:
    """Charge les doc_id déjà retraités (reprise après interruption)."""
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_done(done: set[str]) -> None:
    """Persiste la liste des doc_id retraités (écrit à chaque succès)."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(done), f, ensure_ascii=False)


def fetch_docs(filter_sql: str, limit: int | None) -> list[tuple[str, str]]:
    """Retourne la liste (id, file_path) des documents à réindexer.

    ``limit`` est passé en paramètre (requête paramétrée, pas d'interpolation).
    """
    sql = "SELECT id, file_path FROM documents"
    params: list = []
    if filter_sql:
        sql += " WHERE " + filter_sql
    sql += " ORDER BY file_path"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql, params).fetchall()
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
    ap.add_argument("--reset", action="store_true",
                    help="Efface le suivi de progression et repart de zéro")
    args = ap.parse_args()

    if args.reset:
        try:
            Path(PROGRESS_FILE).unlink()
            print(f"Suivi réinitialisé ({PROGRESS_FILE} supprimé).")
        except FileNotFoundError:
            pass

    done = load_done()
    docs = fetch_docs(args.filter, args.limit)
    # Filtrer les docs déjà retraités (reprise).
    pending = [(did, fp) for did, fp in docs if did not in done]
    skipped = len(docs) - len(pending)
    total = len(pending)
    if total == 0:
        print(f"Aucun document à réindexer ({len(docs)} total, {skipped} déjà faits).")
        return
    print(f"{total} document(s) à réindexer avec vision LLM "
          f"({skipped} déjà retraités, ignorés).", flush=True)
    print("⚠️  Long : ~15-30s par image détectée. Prévoir plusieurs heures.", flush=True)
    print("    Reprise : Ctrl+C puis relancer — le suivi est persisté.", flush=True)
    print("", flush=True)

    # ingest-doc en subprocess (--vision --force) pour chaque doc. --force est
    # requis car le hash du contenu binaire du fichier n'a pas changé ; le
    # suivi de reprise (sidecar JSON) compense le contournement du dédoublonnage.
    ok = 0
    failed = 0
    t0 = time.time()
    for i, (doc_id, file_path) in enumerate(pending, 1):
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
                done.add(doc_id)
                save_done(done)  # persiste immédiatement (reprise fiable)
                # Extraire le nb de chunks du log pour visibilité.
                for line in res.stdout.splitlines():
                    if "chunks" in line.lower():
                        print(f"      {line.strip()}", flush=True)
                        break
            else:
                failed += 1
                print("      ÉCHEC (pas de SUCCESS)", flush=True)
                if res.stderr:
                    print(f"      {res.stderr[:150]}", flush=True)
        except subprocess.TimeoutExpired:
            failed += 1
            print("      TIMEOUT (15 min) — document skippé", flush=True)
        except subprocess.CalledProcessError as e:
            failed += 1
            print(f"      ERREUR: {str(e)[:100]}", flush=True)
        except KeyboardInterrupt:
            print(f"\nInterrompu par l'utilisateur après {i-1} doc(s) retraités. "
                  f"Le suivi est persisté ({PROGRESS_FILE}).", flush=True)
            sys.exit(130)

        # ETA toutes les 5 docs.
        if i % 5 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  ... {i}/{total} faits ({elapsed/60:.0f} min, ETA {eta/60:.0f} min) "
                  f"| OK={ok} ECHEC={failed}", flush=True)

    elapsed = time.time() - t0
    print(f"\n=== Réindexation terminée en {elapsed/60:.0f} min ===", flush=True)
    print(f"Réussis : {ok}/{total} | Échecs : {failed}", flush=True)
    print(f"Suivi : {PROGRESS_FILE} ({len(done)} doc(s) retraités au total).", flush=True)


if __name__ == "__main__":
    main()
