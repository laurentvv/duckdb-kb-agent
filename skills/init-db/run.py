import duckdb

DB_PATH = "knowledge.duckdb"


def init_db(db_path: str = DB_PATH) -> None:
    """Crée la base et les tables si elles n'existent pas.

    Schéma :
      - documents              : id (hash SHA-256) PK
      - document_content       : document_id PK (relation 1:1), embedding FLOAT[1024]
      - document_ai_metadata   : document_id PK, keywords en VARCHAR[] (liste native)
      - chunks                 : id PK, document_id FK, chunk_index, text, element_type,
                                 page_number, section, embedding FLOAT[1024]
                                 (retrieval granulaire au niveau chunk)

    Index :
      - FTS (BM25) sur document_content.raw_text ET sur chunks.text
      - HNSW (cosine) sur document_content.embedding ET sur chunks.embedding
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

        # Table des chunks : granularité sous-document pour le retrieval.
        # Chaque chunk porte son propre embedding (bge-m3) + métadonnées de
        # structure (page, section, type) pour des citations vérifiables.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id VARCHAR PRIMARY KEY,
                document_id VARCHAR,
                chunk_index INTEGER,
                text TEXT,
                parent_text TEXT,
                element_type VARCHAR,
                page_number INTEGER,
                section VARCHAR,
                embedding FLOAT[1024],
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );
            """
        )


        # Table pour stocker les interactions et feedbacks (Évaluation continue)
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS feedbacks (
                id VARCHAR PRIMARY KEY,
                question TEXT,
                rewritten_query TEXT,
                context TEXT,
                answer TEXT,
                rating VARCHAR,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            '''
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
            print("FTS index created (document_content).")
        except Exception as e:
            print(f"FTS index could not be created or already exists: {e}")

        # FTS sur les chunks (retrieval granulaire BM25 au niveau chunk).
        try:
            conn.execute(
                "PRAGMA create_fts_index('chunks', 'id', 'text');"
            )
            print("FTS index created (chunks).")
        except Exception as e:
            print(f"FTS chunks index could not be created or already exists: {e}")

        # --- Extension vss (recherche vectorielle, index HNSW cosine) ---
        # vss est requis pour les index HNSW. Si indisponible (DuckDB sans vss
        # ou hors-ligne non installé), on skippe la création des index vectoriels
        # mais la FTS continue de fonctionner.
        vss_ok = True
        try:
            conn.execute("INSTALL vss;")
        except Exception as e:
            print(f"Info: INSTALL vss ignoré (déjà installé ou hors-ligne) : {e}")
        try:
            conn.execute("LOAD vss;")
        except Exception as e:
            print(f"Warning: extension vss indisponible : {e}")
            print("  -> Les index HNSW ne seront pas créés (recherche vectorielle désactivée).")
            vss_ok = False
        # Sur base persistante, la persistance HNSW est expérimentale : on
        # l'active (APRÈS LOAD vss, AVANT CREATE INDEX). Inoffensif en :memory:.
        try:
            conn.execute("SET hnsw_enable_experimental_persistence = true;")
        except Exception:
            pass
        if vss_ok:
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_content_embedding "
                    "ON document_content USING HNSW (embedding) WITH (metric = 'cosine');"
                )
                print("HNSW embedding index created (document_content).")
            except Exception as e:
                print(f"HNSW index could not be created: {e}")

            # Index HNSW sur les embeddings de chunks (recherche vectorielle chunk-level).
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
                    "ON chunks USING HNSW (embedding) WITH (metric = 'cosine');"
                )
                print("HNSW embedding index created (chunks).")
            except Exception as e:
                print(f"HNSW chunks index could not be created: {e}")

        print("Database initialization complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
