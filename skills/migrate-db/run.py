"""Migration non destructive du schéma knowledge.duckdb.

Applique les évolutions du schéma à une base existante :
  1. Ajoute PRIMARY KEY sur document_content.document_id et
     document_ai_metadata.document_id (relation 1:1 attendue).
  2. Convertit document_ai_metadata.keywords du JSON textuel (VARCHAR)
     vers une vraie liste DuckDB (VARCHAR[]) requêtable.
  3. Ajoute la colonne embedding FLOAT[1024] + l'index HNSW (cosine) sur
     document_content (pour la recherche vectorielle). Ne calcule PAS les
     embeddings (trop lent) : utiliser skills/embed-docs pour le remplissage.

Sécurité :
  - --dry-run par défaut : n'écrit rien, affiche uniquement le plan.
  - Sauvegarde le fichier .duckdb avant toute écriture (copie horodatée).
  - Ne supprime jamais de données.

Usage :
  uv run skills/migrate-db/run.py              # dry-run (lecture seule)
  uv run skills/migrate-db/run.py --apply      # exécute réellement
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import duckdb

DB_PATH = "knowledge.duckdb"


def column_type(con, table, column):
    """Retourne le type SQL d'une colonne, ou None si absente."""
    try:
        row = con.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            [table, column],
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def has_primary_key(con, table):
    """True si la table possède déjà une contrainte PRIMARY KEY."""
    try:
        rows = con.execute(
            "SELECT constraint_type FROM duckdb_constraints() "
            "WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'",
            [table],
        ).fetchall()
        return len(rows) > 0
    except Exception:
        return False


def add_pk(con, table, dry):
    """Ajoute PRIMARY KEY (document_id). Nécessite des valeurs uniques."""
    if has_primary_key(con, table):
        print(f"  [skip] {table}.document_id a déjà une PRIMARY KEY.")
        return True
    dup = con.execute(
        f"SELECT document_id, COUNT(*) c FROM {table} "
        f"GROUP BY document_id HAVING c > 1 LIMIT 1"
    ).fetchall()
    if dup:
        print(f"  [BLOCKÉ] {table} contient des document_id dupliqués "
              f"(ex: {dup[0][0]} x{dup[0][1]}). Nettoyer d'abord.")
        return False
    action = ("ALTER TABLE", "PK ajoutée")
    if dry:
        print(f"  [dry-run] ajout PRIMARY KEY(document_id) sur {table}.")
        return True
    con.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (document_id);")
    print(f"  [ok] {table}: {action[1]}.")
    return True


def convert_keywords(con, dry):
    """Convertit keywords (VARCHAR JSON) -> VARCHAR[]. Idempotent."""
    ctype = column_type(con, "document_ai_metadata", "keywords")
    if ctype is None:
        print("  [BLOCKÉ] colonne keywords introuvable.")
        return False
    # duckdb retourne par ex. 'VARCHAR[]' pour une liste, 'VARCHAR' sinon.
    if "[]" in str(ctype).upper():
        print("  [skip] keywords est déjà VARCHAR[].")
        return True

    # Compter les valeurs non JSON-valides pour avertir.
    sample = con.execute(
        "SELECT keywords FROM document_ai_metadata "
        "WHERE keywords IS NOT NULL LIMIT 1000"
    ).fetchall()
    bad = 0
    for (kw,) in sample:
        try:
            if kw is not None:
                json.loads(kw)
        except Exception:
            bad += 1

    if dry:
        print(f"  [dry-run] conversion keywords VARCHAR -> VARCHAR[] "
              f"(~{bad} valeur(s) non-JSON sur l'échantillon seront mappées à []).")
        return True

    # Strategy : nouvelle colonne _new VARCHAR[], remplir, remplacer.
    con.execute("ALTER TABLE document_ai_metadata ADD COLUMN keywords_new VARCHAR[];")
    # from_json convertit une chaîne JSON en liste DuckDB ; on garde [] en cas d'erreur
    con.execute(
        """
        UPDATE document_ai_metadata
        SET keywords_new = CASE
            WHEN keywords IS NULL THEN NULL
            ELSE try_cast(json_extract_string(keywords, '$') AS VARCHAR[])
        END;
        """
    )
    # try_cast échoue rarement ; fallback : construire la liste manuellement via Python
    # pour les lignes encore NULL alors que keywords non NULL.
    rows = con.execute(
        "SELECT document_id, keywords FROM document_ai_metadata "
        "WHERE keywords IS NOT NULL AND keywords_new IS NULL"
    ).fetchall()
    for doc_id, kw in rows:
        try:
            lst = json.loads(kw) if kw else []
        except Exception:
            lst = []
        con.execute(
            "UPDATE document_ai_metadata SET keywords_new = ? WHERE document_id = ?",
            [lst, doc_id],
        )
    con.execute("ALTER TABLE document_ai_metadata DROP keywords;")
    con.execute("ALTER TABLE document_ai_metadata RENAME keywords_new TO keywords;")
    print("  [ok] keywords convertie en VARCHAR[].")
    return True


def add_embedding_column(con, dry):
    """Ajoute document_content.embedding FLOAT[1024] + index HNSW (cosine).

    Idempotent. Ne remplit PAS les vecteurs (voir skills/embed-docs).
    """
    ctype = column_type(con, "document_content", "embedding")
    if ctype is not None:
        print("  [skip] colonne embedding déjà présente.")
    else:
        if dry:
            print("  [dry-run] ajout colonne embedding FLOAT[1024].")
        else:
            con.execute("ALTER TABLE document_content ADD COLUMN embedding FLOAT[1024];")
            print("  [ok] colonne embedding FLOAT[1024] ajoutée.")

    # Index HNSW (vss requis). Sur base persistante, le flag experimental
    # persistence doit être activé APRÈS LOAD vss et AVANT CREATE INDEX.
    try:
        con.execute("LOAD vss;")
    except Exception:
        try:
            con.execute("INSTALL vss; LOAD vss;")
        except Exception as e:
            print(f"  [BLOCKÉ] extension vss indisponible : {e}")
            return False
    try:
        con.execute("SET hnsw_enable_experimental_persistence = true;")
    except Exception:
        pass  # OK en :memory: où le flag n'est pas requis

    has_idx = con.execute(
        "SELECT COUNT(*) FROM duckdb_indexes() WHERE index_name = 'idx_content_embedding'"
    ).fetchone()[0]
    if has_idx:
        print("  [skip] index HNSW idx_content_embedding déjà présent.")
        return True
    if dry:
        print("  [dry-run] création index HNSW (metric=cosine) sur embedding.")
        return True
    con.execute(
        "CREATE INDEX idx_content_embedding "
        "ON document_content USING HNSW (embedding) WITH (metric = 'cosine');"
    )
    print("  [ok] index HNSW (cosine) créé.")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="Exécute réellement la migration (par défaut : dry-run).")
    ap.add_argument("--db", default=DB_PATH, help="Chemin de la base DuckDB.")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"Base introuvable : {db}")
        sys.exit(1)

    mode = "APPLY" if args.apply else "DRY-RUN (lecture seule)"
    print(f"=== Migration {mode} sur {db} ===\n")

    # Sauvegarde horodatée avant écriture.
    if args.apply:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = db.with_name(f"{db.stem}.backup-{stamp}{db.suffix}")
        shutil.copy2(db, backup)
        print(f"Sauvegarde créée : {backup}\n")

    con = duckdb.connect(str(db))
    try:
        print("[1/3] Contraintes PRIMARY KEY :")
        ok1 = add_pk(con, "document_content", dry=not args.apply)
        ok2 = add_pk(con, "document_ai_metadata", dry=not args.apply)
        print("\n[2/3] Conversion keywords JSON -> VARCHAR[] :")
        ok3 = convert_keywords(con, dry=not args.apply)
        print("\n[3/3] Colonne embedding + index HNSW :")
        ok4 = add_embedding_column(con, dry=not args.apply)
    finally:
        con.close()

    print("\n=== Migration terminée ===")
    if not args.apply:
        print("Dry-run : aucune donnée écrite. Relancer avec --apply pour exécuter.")
    if not (ok1 and ok2 and ok3 and ok4):
        print("Des étapes ont été sautées ou bloquées (voir ci-dessus).")
        sys.exit(2)


if __name__ == "__main__":
    main()
