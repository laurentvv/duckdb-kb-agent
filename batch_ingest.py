"""Ingestion en masse : parcourt un dossier et ingère chaque fichier via le skill ingest-doc.

Usage :
  uv run batch_ingest.py "C:\\chemin\\vers\\dossier"
  uv run batch_ingest.py "C:\\chemin\\vers\\dossier" --category "Tech"
  uv run batch_ingest.py "C:\\chemin\\vers\\dossier" --extensions .pdf .docx
"""

import argparse
import subprocess
from pathlib import Path

DEFAULT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".sql", ".xlsx", ".csv", ".ini", ".conf"}


def get_all_files(directory, exclude_dirs=("_Archives",)):
    """Liste les fichiers récursivement, en excluant certains dossiers."""
    files = []
    for f in Path(directory).rglob("*"):
        if f.is_file() and not any(part in exclude_dirs for part in f.parts):
            files.append(f)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Ingestion en masse depuis un dossier source."
    )
    parser.add_argument("directory", help="Dossier source à parcourir (récursif)")
    parser.add_argument("--category", default="Uncategorized",
                        help="Catégorie appliquée à chaque document ingéré")
    parser.add_argument("--extensions", nargs="+",
                        help="Extensions à ingérer (défaut: pdf docx txt md sql xlsx csv ini conf)")
    args = parser.parse_args()

    target_dir = Path(args.directory)
    if not target_dir.is_dir():
        print(f"Dossier introuvable : {target_dir}")
        return

    allowed = set(args.extensions) if args.extensions else DEFAULT_EXTENSIONS
    if args.extensions:
        allowed = {e if e.startswith(".") else f".{e}" for e in args.extensions}

    files = get_all_files(target_dir)
    print(f"Trouvé {len(files)} fichier(s) au total (hors dossiers exclus).")

    valid_files = [f for f in files if f.suffix.lower() in allowed]
    print(f"{len(valid_files)} fichier(s) à ingérer (extensions: {sorted(allowed)}).")

    success_count = 0
    for idx, f in enumerate(valid_files, 1):
        print(f"[{idx}/{len(valid_files)}] Ingestion de {f.name}...")
        try:
            res = subprocess.run(
                ["uv", "run", "skills/ingest-doc/run.py", str(f), "--category", args.category],
                capture_output=True, text=True, check=True,
            )
            if "SUCCESS" in res.stdout:
                success_count += 1
            else:
                print(f"Échec (pas de SUCCESS) :\n{res.stdout}\n{res.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"Erreur d'exécution pour {f.name} :\n{e}\n{e.stdout}\n{e.stderr}")

    print(f"\nTerminé : {success_count}/{len(valid_files)} fichier(s) ingéré(s).")


if __name__ == "__main__":
    main()
