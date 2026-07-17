"""Tests unitaires du skill ingest-doc : extract_text, get_hash, analyze_text."""

import json
import sys
import types

import pytest

from conftest import load_skill


@pytest.fixture(scope="module")
def ingest():
    """Charge le skill ingest-doc en mockant le module openai au préalable.

    On injecte un faux module openai (OpenAI() factice) avant l'import du skill,
    afin qu'aucune connexion réseau ne soit tentée.
    """
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = lambda **kw: types.SimpleNamespace()
    sys.modules["openai"] = fake_openai
    return load_skill("ingest-doc")


# ---------------------------------------------------------------- extract_text


class TestExtractText:
    def test_txt_utf8(self, ingest, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("contenu café", encoding="utf-8")
        assert ingest.extract_text(str(f)) == "contenu café"

    def test_txt_cp1252_fallback(self, ingest, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_bytes("café résumé".encode("cp1252"))
        assert "café" in ingest.extract_text(str(f))

    def test_unknown_ext_falls_back_to_text(self, ingest, tmp_path):
        f = tmp_path / "note.log"
        f.write_text("ligne une\nligne deux", encoding="utf-8")
        assert "ligne une" in ingest.extract_text(str(f))

    def test_csv_via_pandas(self, ingest, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n3,4", encoding="utf-8")
        text = ingest.extract_text(str(f))
        assert "1" in text and "4" in text


# -------------------------------------------------------------------- get_hash


class TestGetHash:
    def test_deterministic(self, ingest, tmp_path):
        f = tmp_path / "f.bin"
        f.write_bytes(b"abc")
        assert ingest.get_hash(str(f)) == ingest.get_hash(str(f))

    def test_distinct_content(self, ingest, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"abc")
        b.write_bytes(b"abd")
        assert ingest.get_hash(str(a)) != ingest.get_hash(str(b))

    def test_is_sha256_hex(self, ingest, tmp_path):
        f = tmp_path / "f.bin"
        f.write_bytes(b"x")
        h = ingest.get_hash(str(f))
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


# ----------------------------------------------------------------- analyze_text


class TestAnalyzeText:
    def _patch_client(self, ingest, monkeypatch, payload):
        """Remplace le client OpenAI du module par un mock renvoyant ``payload``."""
        msg = types.SimpleNamespace(content=json.dumps(payload))
        choice = types.SimpleNamespace(message=msg)
        resp = types.SimpleNamespace(choices=[choice])
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **kw: resp)
            )
        )
        monkeypatch.setattr(ingest, "OpenAI", lambda **kw: client)

    def test_parses_valid_json(self, ingest, monkeypatch):
        self._patch_client(ingest, monkeypatch,
                           {"summary": "Résumé test", "keywords": ["a", "b"]})
        r = ingest.analyze_text("du texte")
        assert r.summary == "Résumé test"
        assert r.keywords == ["a", "b"]

    def test_fallback_on_invalid_json(self, ingest, monkeypatch):
        msg = types.SimpleNamespace(content="pas du json du tout")
        choice = types.SimpleNamespace(message=msg)
        resp = types.SimpleNamespace(choices=[choice])
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **kw: resp)
            )
        )
        monkeypatch.setattr(ingest, "OpenAI", lambda **kw: client)
        r = ingest.analyze_text("x")
        assert r.summary.startswith("No summary")
        assert r.keywords == ["error", "fallback"]

    def test_fallback_on_incomplete_payload(self, ingest, monkeypatch):
        self._patch_client(ingest, monkeypatch, {"summary": "", "keywords": []})
        r = ingest.analyze_text("x")
        assert r.summary.startswith("No summary")
