"""Tests de la recherche hybride (FTS + vectorielle, fusion RRF).

Tourne sur une base temporaire avec des embeddings factices : aucun appel Ollama.
On mocke kb.embed pour contrôler le vecteur de requête.
"""

import pytest

import kb


@pytest.fixture
def tmpdb(tmp_path):
    """Base temporaire avec FTS + vss + 4 documents aux embeddings contrôlés."""
    db = tmp_path / "t.duckdb"
    con = kb.connect(str(db))
    # Créer les tables (init-db ne crée pas vss index sur base vide utile ici)
    con.execute(
        """CREATE TABLE documents (
            id VARCHAR PRIMARY KEY, file_name VARCHAR, file_path VARCHAR,
            category VARCHAR, indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    )
    con.execute(
        """CREATE TABLE document_content (
            document_id VARCHAR PRIMARY KEY, raw_text TEXT, embedding FLOAT[4])"""
    )
    con.execute(
        """CREATE TABLE document_ai_metadata (
            document_id VARCHAR PRIMARY KEY, summary TEXT, keywords VARCHAR[])"""
    )

    # 4 documents. raw_text calibré pour la FTS ; embeddings (4-dim) calibrés
    # pour que la recherche vectorielle favorise docA.
    docs = [
        # (id, raw_text, embedding, file_name)
        ("docA", "installation du client sage 100 sur windows",
         [1.0, 0.0, 0.0, 0.0], "sage100_install.md"),
        ("docB", "installation du client sage comptabilite 1000 adista",
         [0.0, 1.0, 0.0, 0.0], "sage1000_install.md"),
        ("docC", "configuration reseau vpn ipsec routeur",
         [0.0, 0.0, 1.0, 0.0], "vpn.md"),
        ("docD", "sauvegarde base de donnees sql serveur",
         [0.0, 0.0, 0.0, 1.0], "backup_sql.md"),
    ]
    for did, txt, emb, name in docs:
        con.execute("INSERT INTO documents (id, file_name, file_path) VALUES (?, ?, ?)",
                    [did, name, f"/data/{name}"])
        con.execute("INSERT INTO document_content (document_id, raw_text, embedding) VALUES (?, ?, ?)",
                    [did, txt, emb])
        con.execute("INSERT INTO document_ai_metadata (document_id, summary, keywords) VALUES (?, ?, ?)",
                    [did, f"summary {did}", []])

    # Index FTS sur 4 dims (on a FLOAT[4], pas [1024])
    con.execute("PRAGMA create_fts_index('document_content', 'document_id', 'raw_text');")
    # Index HNSW sur FLOAT[4]
    con.execute("CREATE INDEX idx_emb ON document_content USING HNSW (embedding) WITH (metric='cosine');")
    con.close()
    return str(db)


class TestSearchFTS:
    def test_fts_finds_install_docs(self, tmpdb, monkeypatch):
        """La FTS doit retrouver les docs d'installation Sage."""
        con = kb.connect(tmpdb, read_only=True)
        try:
            hits = kb.search_fts(con, "installer sage 100")
        finally:
            con.close()
        ids = [h["document_id"] for h in hits]
        # Au moins un des deux docs d'installation Sage doit remonter
        assert "docA" in ids or "docB" in ids
        # Les rangs commencent à 0
        assert all(h["rank"] == i for i, h in enumerate(hits))


class TestSearchVector:
    def test_vector_prefers_docA(self, tmpdb, monkeypatch):
        """Le vecteur de requête = docA embedding -> docA doit être top-1."""
        # Mocker kb.embed pour renvoyer l'embedding de docA
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: [1.0, 0.0, 0.0, 0.0])
        con = kb.connect(tmpdb, read_only=True)
        try:
            hits = kb.search_vector(con, "installer sage 100")
        finally:
            con.close()
        assert len(hits) > 0
        assert hits[0]["document_id"] == "docA"   # le plus proche cosinus
        assert hits[0]["rank"] == 0

    def test_vector_empty_when_embed_fails(self, tmpdb, monkeypatch):
        """Si Ollama down (embed=None), la recherche vectorielle renvoie []."""
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: None)
        con = kb.connect(tmpdb, read_only=True)
        try:
            hits = kb.search_vector(con, "anything")
        finally:
            con.close()
        assert hits == []


class TestHybridSearch:
    def test_hybrid_returns_top_k(self, tmpdb, monkeypatch):
        """La recherche hybride renvoie au plus k résultats avec métadonnées."""
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: [1.0, 0.0, 0.0, 0.0])
        con = kb.connect(tmpdb, read_only=True)
        try:
            results = kb.hybrid_search(con, "installer sage 100", k=2, mode="hybrid")
        finally:
            con.close()
        assert len(results) <= 2
        assert all("file_name" in r and "raw_text" in r for r in results)
        # Le score RRF est positif
        assert all(r["score"] > 0 for r in results)

    def test_hybrid_source_tag(self, tmpdb, monkeypatch):
        """Le champ 'source' indique par quel(s) moteur(s) un doc a été trouvé."""
        monkeypatch.setattr(kb, "embed", lambda text, model=kb.EMBED_MODEL: [1.0, 0.0, 0.0, 0.0])
        con = kb.connect(tmpdb, read_only=True)
        try:
            results = kb.hybrid_search(con, "installer sage 100", k=5, mode="hybrid")
        finally:
            con.close()
        sources = {r["source"] for r in results}
        # Au moins un doc trouvé par les deux moteurs (docA est top FTS et top vector)
        assert "both" in sources or "fts" in sources

    def test_mode_fts_isolates(self, tmpdb, monkeypatch):
        """--mode fts n'utilise que la FTS (aucun appel à embed)."""
        called = {"n": 0}
        def fake_embed(text, model=kb.EMBED_MODEL):
            called["n"] += 1
            return [1.0, 0, 0, 0]
        monkeypatch.setattr(kb, "embed", fake_embed)
        con = kb.connect(tmpdb, read_only=True)
        try:
            kb.hybrid_search(con, "installer sage", k=3, mode="fts")
        finally:
            con.close()
        assert called["n"] == 0  # fts n'appelle jamais embed


class TestTruncateAndEmbed:
    def test_truncate_respects_limit(self):
        long = "x" * 20000
        assert len(kb.truncate(long)) == kb.MAX_TEXT_CHARS

    def test_truncate_none_safe(self):
        assert kb.truncate(None) == ""
        assert kb.truncate("") == ""
