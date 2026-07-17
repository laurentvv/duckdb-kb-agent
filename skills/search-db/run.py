"""Moteur de recherche de la base documentaire (hybride FTS + vectoriel).

Modes :
  --mode hybrid  (défaut) : fusion RRF des deux moteurs (le plus robuste)
  --mode fts             : Full-Text Search BM25 uniquement
  --mode vector          : recherche vectorielle (cosine) uniquement

Usage :
  uv run skills/search-db/run.py "mots clés"
  uv run skills/search-db/run.py "installer sage 100" --limit 5 --mode hybrid
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console

# Lib partagée (cwd = racine du projet à l'exécution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import kb  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="Mots clés / question à rechercher")
    parser.add_argument("--limit", type=int, default=3, help="Nombre de résultats (défaut 3)")
    parser.add_argument("--mode", choices=["hybrid", "fts", "vector"], default="hybrid",
                        help="Moteur de recherche (défaut: hybrid)")
    args = parser.parse_args()

    console = Console()
    con = kb.connect(kb.DB_PATH, read_only=True)
    try:
        results = kb.hybrid_search(con, args.query, k=args.limit, mode=args.mode)
    except Exception as e:
        print(f"Error executing search: {e}")
        return
    finally:
        con.close()

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, r in enumerate(results):
        console.print(
            f"[bold blue]Result {i+1}: {r['file_name']}[/bold blue] "
            f"(score: {r['score']:.4f}, via [magenta]{r['source']}[/magenta])"
        )
        console.print(f"Path: {r['file_path']}")
        if r["summary"] and not str(r["summary"]).startswith("No summary"):
            console.print(f"Summary: {r['summary']}")
        snippet = (r["raw_text"] or "")[:200].replace("\n", " ").strip()
        console.print(f"Snippet: {snippet}...\n")


if __name__ == "__main__":
    main()
