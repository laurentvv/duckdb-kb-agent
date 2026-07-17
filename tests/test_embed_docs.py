"""Tests du skill embed-docs (remplissage des embeddings).

Mocke kb.embed pour ne pas appeler Ollama. Vérifie :
  - skip des docs au texte vide.
  - troncature du texte à 8000 car.
  - idempotence (relance ne recalcule pas).
  - --rebuild force le recalcul.
"""

import sys

import pytest

import kb
from conftest import load_skill


@pytest.fixture(scope="module")
def embed_skill():
    """Charge le module du skill embed-docs."""
    return load_skill("embed-docs")


@pytest.fixture
def tmpdb(tmp_path):
    """Base avec 3 documents : un normal, un long, un texte vide."""
    db = tmp_path / "t.duckdb"
    con = kb.connect(str(db))
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
    docs = [
        ("d1", "installation sage 100", "sage100.md"),
        ("d2", "x" * 20000, "long.md"),           # > 8000 car
        ("d3", "", "empty.md"),                    # texte vide
    ]
    for did, txt, name in docs:
        con.execute("INSERT INTO documents (id, file_name, file_path) VALUES (?,?,?)",
                    [did, name, f"/data/{name}"])
        con.execute("INSERT INTO document_content (document_id, raw_text) VALUES (?,?)",
                    [did, txt])
    con.close()
    return str(db)


def run_skill(embed_skill, tmpdb, *extra):
    """Lance main() avec argv = [--db tmpdb, ...extra]. Renvoie les textes capturés."""
    captured = []

    def fake_embed(text, model=kb.EMBED_MODEL):
        captured.append(len(text))
        return [0.1, 0.2, 0.3, 0.4]

    old = sys.argv
    sys.argv = ["embed-docs", "--db", tmpdb, *extra]
    try:
        # kb est partagé : on patche sur le module référencé par le skill
        import kb as kb_global
        orig = kb_global.embed
        kb_global.embed = fake_embed
        try:
            embed_skill.main()
        finally:
            kb_global.embed = orig
    finally:
        sys.argv = old
    return captured


class TestEmbedDocs:
    def test_embeds_non_empty_docs(self, embed_skill, tmpdb):
        """embed-docs traite les docs avec texte, skip les vides."""
        run_skill(embed_skill, tmpdb)
        con = kb.connect(tmpdb, read_only=True)
        try:
            res = con.execute(
                "SELECT document_id, embedding IS NOT NULL FROM document_content ORDER BY document_id"
            ).fetchall()
        finally:
            con.close()
        emb = dict(res)
        assert emb["d1"] is True
        assert emb["d2"] is True
        assert emb["d3"] is False   # texte vide -> pas d'embedding

    def test_truncates_long_docs(self, embed_skill, tmpdb):
        """Le texte envoyé à embed est tronqué à MAX_TEXT_CHARS (8000)."""
        captured = run_skill(embed_skill, tmpdb)
        assert all(l <= kb.MAX_TEXT_CHARS for l in captured)

    def test_idempotent(self, embed_skill, tmpdb):
        """Une 2e exécution ne recalcule rien (tous déjà embeddés)."""
        first = len(run_skill(embed_skill, tmpdb))
        second = len(run_skill(embed_skill, tmpdb))
        assert first == 2      # d1 + d2
        assert second == 0     # déjà embeddés

    def test_rebuild_forces_recompute(self, embed_skill, tmpdb):
        """--rebuild recalcule même les docs déjà embeddés."""
        first = len(run_skill(embed_skill, tmpdb))
        rebuilt = len(run_skill(embed_skill, tmpdb, "--rebuild"))
        assert first == 2
        assert rebuilt == 2    # recalcul (d3 reste skippé : texte vide)
