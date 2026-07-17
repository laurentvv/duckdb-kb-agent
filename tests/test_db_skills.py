"""Tests des skills init-db et migrate-db sur des bases temporaires isolées.

Ces tests NE touchent jamais à knowledge.duckdb : ils travaillent sur des
fichiers temporaires (tmp_path) ou :memory:.
"""

import json

import duckdb
import pytest

from conftest import load_skill


# --------------------------------------------------------------------- init-db


class TestInitDb:
    def test_creates_all_tables(self, tmp_path):
        init_db = load_skill("init-db")
        db = tmp_path / "test.duckdb"
        init_db.init_db(str(db))

        con = duckdb.connect(str(db), read_only=True)
        try:
            tables = {
                r[0] for r in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
            assert {"documents", "document_content", "document_ai_metadata"} <= tables
        finally:
            con.close()

    def test_primary_keys_and_keywords_type(self, tmp_path):
        init_db = load_skill("init-db")
        db = tmp_path / "test.duckdb"
        init_db.init_db(str(db))

        con = duckdb.connect(str(db), read_only=True)
        try:
            con.execute("LOAD vss;")
            # document_content.document_id doit être PK
            dc = {r[0]: r for r in con.execute("DESCRIBE document_content").fetchall()}
            assert dc["document_id"][3] == "PRI"

            # keywords doit être VARCHAR[]
            meta = {r[0]: r for r in con.execute("DESCRIBE document_ai_metadata").fetchall()}
            assert "[]" in str(meta["keywords"][1]).upper()

            # embedding doit être FLOAT[1024]
            assert "embedding" in dc
            assert "1024" in str(dc["embedding"][1])

            # index HNSW présent
            idx = con.execute(
                "SELECT COUNT(*) FROM duckdb_indexes() WHERE index_name='idx_content_embedding'"
            ).fetchone()[0]
            assert idx == 1
        finally:
            con.close()

    def test_idempotent(self, tmp_path):
        init_db = load_skill("init-db")
        db = tmp_path / "test.duckdb"
        init_db.init_db(str(db))
        init_db.init_db(str(db))  # ne doit pas lever d'erreur


# ------------------------------------------------------------------ migrate-db


class TestMigrateDb:
    def _make_old_schema(self, db_path):
        """Crée une base avec l'ANCIEN schéma (pas de PK, keywords en VARCHAR JSON)."""
        con = duckdb.connect(str(db_path))
        con.execute("""CREATE TABLE documents (
            id VARCHAR PRIMARY KEY, file_name VARCHAR, file_path VARCHAR,
            category VARCHAR, indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE document_content (
            document_id VARCHAR, raw_text TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id))""")
        con.execute("""CREATE TABLE document_ai_metadata (
            document_id VARCHAR, summary TEXT, keywords TEXT,
            FOREIGN KEY (document_id) REFERENCES documents(id))""")
        # 2 lignes, dont une avec keywords NULL
        con.execute("INSERT INTO documents (id) VALUES ('d1'), ('d2')")
        con.execute("INSERT INTO document_content VALUES ('d1','texte'),('d2','texte')")
        con.execute(
            "INSERT INTO document_ai_metadata VALUES ('d1','sommaire', ?),('d2',NULL,NULL)",
            [json.dumps(["alpha", "beta"])],
        )
        con.close()

    def test_dry_run_does_not_modify(self, tmp_path, capsys):
        migrate = load_skill("migrate-db")
        db = tmp_path / "old.duckdb"
        self._make_old_schema(db)

        rc = migrate.main.__wrapped__ if hasattr(migrate.main, "__wrapped__") else None
        # On appelle via argparse en mockant sys.argv
        import sys
        old_argv = sys.argv
        sys.argv = ["migrate", "--db", str(db)]
        try:
            migrate.main()
        except SystemExit as e:
            assert e.code == 0
        finally:
            sys.argv = old_argv

        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        # Aucun backup créé en dry-run
        assert not list(tmp_path.glob("*.backup-*"))

        # Vérifie que le schéma est inchangé (keywords toujours VARCHAR, pas de PK sur content)
        con = duckdb.connect(str(db), read_only=True)
        try:
            meta = {r[0]: r for r in con.execute("DESCRIBE document_ai_metadata").fetchall()}
            assert "[]" not in str(meta["keywords"][1]).upper()
        finally:
            con.close()

    def test_apply_converts_schema(self, tmp_path):
        migrate = load_skill("migrate-db")
        db = tmp_path / "old.duckdb"
        self._make_old_schema(db)

        import sys
        old_argv = sys.argv
        sys.argv = ["migrate", "--apply", "--db", str(db)]
        try:
            migrate.main()
        except SystemExit as e:
            assert e.code == 0
        finally:
            sys.argv = old_argv

        con = duckdb.connect(str(db), read_only=True)
        try:
            # PK ajoutée sur document_content
            dc = {r[0]: r for r in con.execute("DESCRIBE document_content").fetchall()}
            assert dc["document_id"][3] == "PRI"
            # keywords devenue VARCHAR[]
            meta = {r[0]: r for r in con.execute("DESCRIBE document_ai_metadata").fetchall()}
            assert "[]" in str(meta["keywords"][1]).upper()
            # Données préservées : d1 a sa liste, d2 reste NULL
            rows = {
                r[0]: r[1]
                for r in con.execute(
                    "SELECT document_id, keywords FROM document_ai_metadata"
                ).fetchall()
            }
            assert rows["d1"] == ["alpha", "beta"]
            assert rows["d2"] is None
        finally:
            con.close()
