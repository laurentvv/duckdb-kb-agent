"""Vision LLM — OCR/description des images via un modèle multimodal local (Ollama).

Comble le trou fonctionnel : les images (PDF scannés, images embarquées DOCX,
fichiers .png/.jpg isolés) sont normalement ignorées par l'extraction. Ce
module les envoie à un **modèle de vision** (Gemma 4 E4B, multimodal, déjà
utilisé pour le chat/résumé) qui produit une transcription/description en
Markdown, ensuite indexée comme un chunk normal.

Design :
  - **Opt-in** : la vision est désactivée par défaut (coût ~15-30s/image).
    Active via ``KB_VISION_ENABLED=1`` ou ``--vision`` (CLI ingest-doc).
  - **Non bloquant** : si le VLM échoue (Ollama down, modèle absent, timeout),
    l'image est skippée (``describe_image`` retourne ``None``), l'ingestion
    continue — cohérent avec le pattern des embeddings.
  - **Réutilise le prompt OCR** de ``pdf-ocr-ai`` (transcription verbatim,
    tables Markdown, description UI/graphiques, sortie français) mais fait
    l'appel nous-même (timeout configurable, vs 60s dur dans pdf-ocr-ai).
  - **Même modèle que le chat** : Gemma 4 E4B est multimodal, aucun modèle
    supplémentaire à puller.

Ne dépend d'aucun cloud : 100% local via Ollama (API OpenAI-compatible /v1).
"""

from __future__ import annotations

import base64
import time
from typing import Optional

import kb

# Prompt OCR réutilisé de pdf-ocr-ai (calibré pour la transcription de docs
# métier FR : texte verbatim, tables Markdown, description UI/graphiques).
# Import paresseux pour garder le module importable même si pdf-ocr-ai manque.
def _load_ocr_prompt() -> str:
    try:
        from pdf_ocr_ai.providers import OCR_PROMPT  # type: ignore
        return OCR_PROMPT
    except Exception:
        # Repli : prompt minimal si pdf-ocr-ai n'est pas installé.
        return (
            "Extract all text verbatim from this image. Preserve reading order "
            "and structure (tables as Markdown, lists). Describe UI/charts. "
            "Output in structured Markdown."
        )


def is_enabled(override: bool | None = None) -> bool:
    """True si la vision est activée.

    ``override`` (depuis --vision CLI) force l'activation si True ; sinon on
    lit ``kb.VISION_ENABLED`` (env KB_VISION_ENABLED).
    """
    if override is not None:
        return override or kb.VISION_ENABLED
    return kb.VISION_ENABLED


def describe_image(image_bytes: bytes, mime: str = "image/png") -> Optional[str]:
    """Envoie une image au VLM, renvoie la description Markdown ou None si échec.

    Non bloquant : aucune exception n'est propagée (l'image est skippée en cas
    d'erreur). Retry léger (2 tentatives, backoff 2s) pour absorber les
    surcharges transitoires d'Ollama.
    """
    if not image_bytes:
        return None
    from openai import OpenAI  # import paresseux

    prompt = _load_ocr_prompt()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    # Le type MIME est transmis dans le data-URI ; défaut image/png.
    mime = mime if mime and mime.startswith("image/") else "image/png"
    client = OpenAI(base_url=kb.LLM_BASE_URL, api_key="ollama",
                    timeout=kb.VISION_TIMEOUT)

    last_exc = None
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=kb.VISION_MODEL,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }],
                max_tokens=2048,
                temperature=0.1,
            )
            content = (resp.choices[0].message.content or "").strip()
            return content or None
        except Exception as e:
            last_exc = e
            if attempt == 0:
                time.sleep(2)  # backoff avant retry
    # Échec définitif : on skippe l'image sans crasher l'ingestion.
    print(f"  [vision] ECHEC description image ({last_exc})" if last_exc else "")
    return None


def rasterize_page_to_png(pdf_path: str, page_number_1based: int,
                          dpi: int | None = None) -> bytes:
    """Rasterise une page PDF en PNG (bytes) via PyMuPDF.

    ``page_number_1based`` : numéro de page en base 1 (cohérent avec l'extraction
    pdfplumber). Utilisé pour les PDF scannés/pages image envoyés au VLM.
    """
    import fitz  # type: ignore  # noqa: PLC0415

    dpi = dpi or kb.VISION_DPI
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_number_1based - 1]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
