"""Recrée l'index Full-Text Search (FTS) de knowledge.duckdb.

À exécuter après des ingestions massives ou si les résultats de recherche
deviennent incohérents. L'ancien index est d'abord supprimé puis recréé.

Note technique : le drop puis le create sont faits dans deux connexions
séparées. Dans la même session, DuckDB lève
« subject 'stopwords' has been deleted » car l'objet stopwords de l'extension
FTS est nettoyé lors du drop.

Usage :
  uv run skills/reindex/run.py
"""

import duckdb

DB_PATH = "knowledge.duckdb"


def reindex(db_path: str = DB_PATH) -> None:
    # 1. Suppression de l'ancien index (connexion dédiée).
    con = duckdb.connect(db_path)
    try:
        con.execute("LOAD fts;")
        try:
            con.execute("PRAGMA drop_fts_index('document_content');")
            print("Ancien index FTS supprimé.")
        except Exception as e:
            print(f"Pas d'ancien index à supprimer (ignoré) : {e}")
    finally:
        con.close()

    # 2. Recréation dans une connexion fraîche (évite le bug 'stopwords').
    con = duckdb.connect(db_path)
    try:
        con.execute("LOAD fts;")
        con.execute(
            "PRAGMA create_fts_index('document_content', 'document_id', 'raw_text');"
        )
        print("Index FTS recréé.")
    finally:
        con.close()


if __name__ == "__main__":
    reindex()
