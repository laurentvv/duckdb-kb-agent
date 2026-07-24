"""Tests de la recherche hybride au niveau chunk (FTS + vectorielle, RRF).

Tourne sur une base temporaire avec une table chunks peuplée et des embeddings
factices (4-dim) : aucun appel Ollama. On mocke kb.embed pour le vecteur requête.
"""

import duckdb
import pytest

import kb


@pytest.fixture
def tmpdb(tmp_path):
    """Base temporaire avec tables documents + chunks, FTS et HNSW (4-dim)."""
    db = tmp_path / "t.duckdb"
    con = kb.connect(str(db))
    con.execute(
        """CREATE TABLE documents (
            id VARCHAR PRIMARY KEY, file_name VARCHAR, file_path VARCHAR,
            category VARCHAR, indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    )
    con.execute(
        """CREATE TABLE document_ai_metadata (
            document_id VARCHAR PRIMARY KEY, summary TEXT, keywords VARCHAR[])"""
    )
    con.execute(
        """CREATE TABLE chunks (
            id VARCHAR PRIMARY KEY, document_id VARCHAR, chunk_index INTEGER,
            text TEXT, element_type VARCHAR, page_number INTEGER,
            section VARCHAR, embedding FLOAT[4])"""
    )

    # 2 documents, chacun découpé en 2 chunks. Embeddings 4-dim calibrés pour
    # favoriser le chunk "install sage 100" (docA-c0).
    data = [
        # (chunk_id, doc_id, idx, text, etype, page, section, embedding, file_name)
        ("docA-c0", "docA", 0, "installation du client sage 100 sur windows",
         "NarrativeText", 1, "Installation", [1.0, 0.0, 0.0, 0.0], "sage100.md"),
        ("docA-c1", "docA", 1, "configuration reseau et pare-feu sage 100",
         "NarrativeText", 2, "Réseau", [0.9, 0.1, 0.0, 0.0], "sage100.md"),
        ("docB-c0", "docB", 0, "sauvegarde base sql serveur automate",
         "Table", 1, "Sauvegarde", [0.0, 0.0, 0.1, 1.0], "backup.md"),
        ("docB-c1", "docB", 1, "restauration plan de reprise activite",
         "NarrativeText", 5, "Restauration", [0.0, 0.0, 0.0, 0.9], "backup.md"),
    ]
    for cid, did, idx, txt, et, pg, sec, emb, name in data:
        con.execute(
            """INSERT INTO chunks (id, document_id, chunk_index, text, element_type,
               page_number, section, embedding) VALUES (?,?,?,?,?,?,?,?)""",
            [cid, did, idx, txt, et, pg, sec, emb],
        )
    # Documents et metadata (une fois chacun).
    con.execute("INSERT INTO documents (id, file_name, file_path) VALUES ('docA','sage100.md','/data/sage100.md')")
    con.execute("INSERT INTO documents (id, file_name, file_path) VALUES ('docB','backup.md','/data/backup.md')")
    con.execute("INSERT INTO document_ai_metadata (document_id, summary, keywords) VALUES ('docA','summary docA',[])")
    con.execute("INSERT INTO document_ai_metadata (document_id, summary, keywords) VALUES ('docB','summary docB',[])")

    con.execute("PRAGMA create_fts_index('chunks', 'id', 'text');")
    con.execute("CREATE INDEX idx_chunks_emb ON chunks USING HNSW (embedding) WITH (metric='cosine');")
    con.close()
    return str(db)


class TestSearchFtsChunks:
    def test_fts_finds_sage_chunk(self, tmpdb):
        con = kb.connect(tmpdb, read_only=True)
        try:
            hits = kb.search_fts_chunks(con, "installer sage 100")
        finally:
            con.close()
        ids = [h["chunk_id"] for h in hits]
        assert "docA-c0" in ids or "docA-c1" in ids
        assert all(h["rank"] == i for i, h in enumerate(hits))


class TestSearchVectorChunks:
    def test_vector_prefers_docA_c0(self, tmpdb, monkeypatch):
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: [1.0, 0.0, 0.0, 0.0])
        con = kb.connect(tmpdb, read_only=True)
        try:
            hits = kb.search_vector_chunks(con, "installer sage")
        finally:
            con.close()
        assert hits[0]["chunk_id"] == "docA-c0"
        assert hits[0]["rank"] == 0

    def test_vector_empty_on_embed_fail(self, tmpdb, monkeypatch):
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: None)
        con = kb.connect(tmpdb, read_only=True)
        try:
            hits = kb.search_vector_chunks(con, "x")
        finally:
            con.close()
        assert hits == []


class TestHybridSearchChunks:
    def test_returns_chunks_with_metadata(self, tmpdb, monkeypatch):
        """hybrid_search_chunks renvoie des chunks avec text/page/section/file_name."""
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: [1.0, 0.0, 0.0, 0.0])
        con = kb.connect(tmpdb, read_only=True)
        try:
            results = kb.hybrid_search_chunks(con, "installer sage 100", k=3, mode="hybrid")
        finally:
            con.close()
        assert len(results) > 0
        r = results[0]
        # Champs attendus présents.
        for key in ("chunk_id", "document_id", "text", "element_type",
                    "page_number", "section", "file_name", "summary", "score", "source"):
            assert key in r
        assert r["file_name"] == "sage100.md"
        assert r["page_number"] is not None

    def test_max_chunks_per_doc_caps_results(self, tmpdb, monkeypatch):
        """Au plus max_chunks_per_doc chunks par document."""
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: [1.0, 0.0, 0.0, 0.0])
        con = kb.connect(tmpdb, read_only=True)
        try:
            results = kb.hybrid_search_chunks(con, "sage", k=10, mode="hybrid", max_chunks_per_doc=1)
        finally:
            con.close()
        doc_ids = [r["document_id"] for r in results]
        # docA ne doit apparaître qu'une fois (cap = 1).
        assert doc_ids.count("docA") <= 1

    def test_mode_fts_no_embed_call(self, tmpdb, monkeypatch):
        called = {"n": 0}

        def fake(text, model=kb.EMBED_MODEL):
            called["n"] += 1
            return [1.0, 0, 0, 0]

        monkeypatch.setattr(kb, "embed", fake)
        con = kb.connect(tmpdb, read_only=True)
        try:
            kb.hybrid_search_chunks(con, "installer sage", k=3, mode="fts")
        finally:
            con.close()
        assert called["n"] == 0
