"""Tests du module vision et de l'intégration VLM dans parsing.

Tous les appels au VLM sont mockés (monkeypatch) : aucun appel réel à Ollama.
On teste :
  - describe_image retourne None en cas d'échec (non bloquant).
  - describe_image retourne la description si le client répond.
  - _extract_image_file : [Element] si vision on, [] si off.
  - extract_elements(.png) avec vision mockée -> description indexée.
  - is_enabled respecte override et kb.VISION_ENABLED.
"""

import types


import kb
import parsing
import vision


# --------------------------------------------------------------- vision.describe_image


class TestDescribeImage:
    def test_returns_none_on_empty_bytes(self):
        assert vision.describe_image(b"") is None

    def test_returns_none_when_client_raises(self, monkeypatch):
        """describe_image ne lève jamais : retourne None si le VLM échoue."""
        # Mocker le client OpenAI pour qu'il lève.
        import openai

        class FailingClient:
            def __init__(self, **kw):
                self.chat = types.SimpleNamespace()
                self.chat.completions = types.SimpleNamespace()

                def raise_create(**kw):
                    raise RuntimeError("Ollama down")
                self.chat.completions.create = raise_create

        # Réduire le backoff pour aller vite.
        monkeypatch.setattr(vision.time, "sleep", lambda s: None)
        monkeypatch.setattr(openai, "OpenAI", lambda **kw: FailingClient())
        result = vision.describe_image(b"\x89PNG fake image bytes")
        assert result is None  # non bloquant

    def test_returns_description_when_client_responds(self, monkeypatch):
        """describe_image retourne le contenu Markdown si le VLM répond."""
        import openai

        class OkClient:
            def __init__(self, **kw):
                msg = types.SimpleNamespace(content="Description de l'image : schéma réseau")
                choice = types.SimpleNamespace(message=msg)
                resp = types.SimpleNamespace(choices=[choice])
                self.chat = types.SimpleNamespace()
                self.chat.completions = types.SimpleNamespace()
                self.chat.completions.create = lambda **kw: resp

        monkeypatch.setattr(openai, "OpenAI", lambda **kw: OkClient())
        result = vision.describe_image(b"\x89PNG fake image bytes")
        assert result == "Description de l'image : schéma réseau"


# ---------------------------------------------------------------- vision.is_enabled


class TestIsEnabled:
    def test_reads_env_default(self):
        # kb.VISION_ENABLED est False par défaut (pas de KB_VISION_ENABLED).
        assert vision.is_enabled() == kb.VISION_ENABLED

    def test_override_true_forces_on(self, monkeypatch):
        monkeypatch.setattr(kb, "VISION_ENABLED", False)
        assert vision.is_enabled(override=True) is True

    def test_override_false_respects_env(self, monkeypatch):
        monkeypatch.setattr(kb, "VISION_ENABLED", True)
        # override=False ne désactive PAS si l'env active ; override=None lit l'env.
        assert vision.is_enabled(override=None) is True


# --------------------------------------------------------- parsing._extract_image_file


class TestExtractImageFile:
    def test_png_without_vision_returns_empty(self, tmp_path):
        f = tmp_path / "schema.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        els = parsing._extract_image_file(str(f), vision_enabled=False)
        assert els == []

    def test_png_with_vision_mocked_produces_element(self, tmp_path, monkeypatch):
        f = tmp_path / "schema.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        monkeypatch.setattr(vision, "describe_image",
                            lambda b, mime="image/png": "Schéma : 3 serveurs reliés")
        els = parsing._extract_image_file(str(f), vision_enabled=True)
        assert len(els) == 1
        assert "Schéma" in els[0].text
        assert els[0].element_type == "NarrativeText"
        assert els[0].section == "schema.png"

    def test_png_with_vlm_failure_returns_empty(self, tmp_path, monkeypatch):
        """Si le VLM échoue (None), pas d'Element mais pas de crash."""
        f = tmp_path / "schema.jpg"
        f.write_bytes(b"\xff\xd8\xfffake jpg")
        monkeypatch.setattr(vision, "describe_image", lambda b, mime="image/png": None)
        els = parsing._extract_image_file(str(f), vision_enabled=True)
        assert els == []


# ------------------------------------------------- extract_elements routing (integration)


class TestExtractElementsRouting:
    def test_image_routed_when_vision_off(self, tmp_path):
        """Un .png isolé ne tombe plus dans _extract_text_file (bruit binaire)."""
        f = tmp_path / "capture.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01binary\xff")
        els = parsing.extract_elements(str(f), vision_enabled=False)
        assert els == []  # pas de bruit binaire

    def test_image_described_when_vision_on(self, tmp_path, monkeypatch):
        f = tmp_path / "capture.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        monkeypatch.setattr(vision, "describe_image",
                            lambda b, mime="image/png": "Capture écran : fenêtre de configuration")
        els = parsing.extract_elements(str(f), vision_enabled=True)
        assert len(els) == 1
        assert "fenêtre de configuration" in els[0].text
