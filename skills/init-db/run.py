import duckdb

DB_PATH = "knowledge.duckdb"


def init_db(db_path: str = DB_PATH) -> None:
    """Crée la base et les tables si elles n'existent pas.

    Schéma :
      - documents              : id (hash SHA-256) PK
      - document_content       : document_id PK (relation 1:1), embedding FLOAT[1024]
      - document_ai_metadata   : document_id PK, keywords en VARCHAR[] (liste native)

    Index :
      - FTS (BM25) sur document_content.raw_text
      - HNSW (cosine) sur document_content.embedding  (recherche vectorielle)
    """
    conn = duckdb.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id VARCHAR PRIMARY KEY,
                file_name VARCHAR,
                file_path VARCHAR,
                category VARCHAR,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_content (
                document_id VARCHAR PRIMARY KEY,
                raw_text TEXT,
                embedding FLOAT[1024],
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_ai_metadata (
                document_id VARCHAR PRIMARY KEY,
                summary TEXT,
                keywords VARCHAR[],
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );
            """
        )

        # --- Extension FTS (BM25) ---
        try:
            conn.execute("INSTALL fts;")
        except Exception as e:
            print(f"Info: INSTALL fts ignoré (déjà installé ou hors-ligne) : {e}")
        conn.execute("LOAD fts;")

        try:
            conn.execute(
                "PRAGMA create_fts_index('document_content', 'document_id', 'raw_text');"
            )
            print("FTS index created.")
        except Exception as e:
            print(f"FTS index could not be created or already exists: {e}")

        # --- Extension vss (recherche vectorielle, index HNSW cosine) ---
        try:
            conn.execute("INSTALL vss;")
        except Exception as e:
            print(f"Info: INSTALL vss ignoré (déjà installé ou hors-ligne) : {e}")
        conn.execute("LOAD vss;")
        # Sur base persistante, la persistance HNSW est expérimentale : on
        # l'active (APRÈS LOAD vss, AVANT CREATE INDEX). Inoffensif en :memory:.
        try:
            conn.execute("SET hnsw_enable_experimental_persistence = true;")
        except Exception:
            pass
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_content_embedding "
                "ON document_content USING HNSW (embedding) WITH (metric = 'cosine');"
            )
            print("HNSW embedding index created.")
        except Exception as e:
            print(f"HNSW index could not be created: {e}")

        print("Database initialization complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
