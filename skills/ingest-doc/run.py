import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import duckdb
from pydantic import BaseModel
from openai import OpenAI

# Lib partagée (cwd = racine du projet à l'exécution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import kb  # noqa: E402
import parsing  # noqa: E402  # extraction structurée + chunking

class DocAnalysis(BaseModel):
    summary: str
    keywords: list[str]

def extract_text(file_path):
    """Wrapper de compatibilité : renvoie le texte complet (concaténation des éléments).

    Conservé pour les tests existants et pour le résumé LLM. Préférer
    ``parsing.extract_elements`` qui conserve la structure (pages, sections, tables).
    """
    try:
        elements = parsing.extract_elements(file_path)
        text = parsing.elements_to_text(elements)
        if text:
            return text
    except Exception:
        pass
    # Repli sur l'ancien comportement (extraction brute par extension).
    return _extract_text_legacy(file_path)


def _extract_text_legacy(file_path):
    """Ancienne logique d'extraction (repli si parsing.extract_elements échoue)."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        import fitz  # noqa: PLC0415  # import paresseux (repli rare)
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    elif ext == '.docx':
        import docx  # noqa: PLC0415
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    elif ext == '.csv':
        import pandas as pd  # noqa: PLC0415
        df = pd.read_csv(file_path)
        return df.to_string()
    elif ext == '.xlsx':
        import pandas as pd  # noqa: PLC0415
        df = pd.read_excel(file_path)
        return df.to_string()
    else:
        # Tentative UTF-8 puis repli cp1252 (Windows), caractères invalides remplacés
        for enc in ("utf-8", "cp1252"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        # Dernier recours : UTF-8 en remplaçant les caractères invalides
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

def get_hash(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            sha256.update(block)
    return sha256.hexdigest()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL")


def analyze_text(text):
    words = text.split()
    if len(words) > 5000:
        head = " ".join(words[:2500])
        tail = " ".join(words[-2500:])
        content_to_analyze = f"Tête du document:\n{head}\n...\nQueue du document:\n{tail}"
    else:
        content_to_analyze = text

    # Modèle local Ollama (compatible API OpenAI). On demande du JSON et on
    # parse manuellement : Ollama ne supporte pas le Structured Output Pydantic.
    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    system_prompt = (
        "Tu es un analyseur de documents. Résume le texte en français et "
        "extrais les mots-clés pertinents. Réponds UNIQUEMENT avec un objet "
        'JSON de la forme {"summary": "...", "keywords": ["...", "..."]}.'
    )
    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_to_analyze},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        summary = str(data.get("summary", "")).strip()
        keywords_raw = data.get("keywords", [])
        keywords = [str(k).strip() for k in keywords_raw if str(k).strip()]
        if not summary or not keywords:
            raise ValueError("Réponse JSON incomplète (summary/keywords vides).")
        return DocAnalysis(summary=summary, keywords=keywords)
    except Exception as e:
        print(f"Warning: LLM analysis failed: {e}")
        return DocAnalysis(
            summary="No summary available (LLM failed)",
            keywords=["error", "fallback"],
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", help="Path to the file to ingest")
    parser.add_argument("--category", default="Uncategorized", help="Category of the document")
    parser.add_argument("--no-chunks", action="store_true",
                        help="Désactive le chunking (compat/régression : niveau document uniquement)")
    parser.add_argument("--force", action="store_true",
                        help="Force la ré-ingestion même si le contenu est identique "
                             "(recalcule summary/embeddings/chunks)")
    parser.add_argument("--vision", action="store_true",
                        help="Active la vision LLM : OCR/description des images "
                             "(PDF scannés, images DOCX, .png/.jpg isolés). "
                             "Coût ~15-30s/image. Aussi activable via KB_VISION_ENABLED=1.")
    args = parser.parse_args()
    vision_enabled = args.vision or kb.VISION_ENABLED

    if not os.path.exists(args.file_path):
        print(f"File not found: {args.file_path}")
        return

    # 1. Hash d'abord (lecture binaire, rapide)
    print("Generating hash...")
    doc_id = get_hash(args.file_path)

    # 2. Dédoublonnage intelligent AVANT l'extraction/l'analyse LLM (coûteuses).
    #    - Si le contenu est identique (même hash) : skip (déjà à jour).
    #    - Si le même file_path existe mais avec un hash différent (doc modifié) :
    #      on supprime l'ancienne version (document + chunks + contenu) avant de
    #      ré-ingérer la nouvelle. Évite les versions obsolètes en base.
    #    - --force force la ré-ingestion même si le contenu est identique.
    conn = duckdb.connect("knowledge.duckdb")
    try:
        # (a) Contenu identique ?
        if not args.force:
            res = conn.execute(
                "SELECT id FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if res:
                print(f"Document unchanged (hash {doc_id[:12]}...). Skip.")
                return
        # (b) Ancienne version par file_path ? (document modifié entre-temps)
        old = conn.execute(
            "SELECT id FROM documents WHERE file_path = ?", (args.file_path,)
        ).fetchone()
    finally:
        conn.close()
    old_id = old[0] if old else None
    if old_id:
        print(f"Document modified: removing old version {old_id[:12]}... "
              f"(was ingested with different content).")
        _purge_document(old_id)

    # 2b. Vérifier que la base supporte l'écriture sur tables indexées HNSW
    # (vss doit être chargé ; on s'en assure via kb.connect côté insertion).

    # 3. Extraction structurée (éléments avec page/section/type) puis chunking
    if vision_enabled:
        print(f"Extracting elements from {args.file_path} (vision LLM active)...")
    else:
        print(f"Extracting elements from {args.file_path}...")
    chunks = []  # liste de parsing.Chunk
    try:
        if args.no_chunks:
            text = extract_text(args.file_path)
            elements = []
        else:
            elements = parsing.extract_elements(args.file_path, vision_enabled=vision_enabled)
            text = parsing.elements_to_text(elements)
            chunks = parsing.chunk_elements(elements)
            print(f"  -> {len(elements)} éléments, {len(chunks)} chunks.")
    except Exception as e:
        print(f"Error extracting text: {e}")
        return

    if not text.strip():
        print("Warning: extracted text is empty (PDF scanné sans OCR ?). Abandon.")
        return

    # 4. Analyse LLM
    print("Analyzing text with LLM...")
    analysis = analyze_text(text)

    # 5. Embedding vectoriel au niveau document (non bloquant)
    print("Computing document embedding (bge-m3)...")
    embedding = kb.embed(kb.truncate(text))
    if embedding is None:
        print("Warning: embedding échoué (Ollama/bge-m3 down ?) -> doc ingéré sans vecteur.")

    # 5b. Embeddings des chunks (non bloquant)
    chunk_rows = []  # (id, doc_id, chunk_index, text, element_type, page_number, section, embedding)
    if chunks:
        print(f"Computing embeddings for {len(chunks)} chunks...")
        embed_ok = 0
        for ch in chunks:
            ch_id = kb.get_chunk_id(doc_id, ch.chunk_index)
            vec = kb.embed(kb.truncate(ch.text)) if ch.text.strip() else None
            if vec is not None:
                embed_ok += 1
            chunk_rows.append((ch_id, doc_id, ch.chunk_index, ch.text,
                               ch.element_type, ch.page_number, ch.section, vec))
        print(f"  -> {embed_ok}/{len(chunks)} chunks embeddés.")

    # 6. Insertion transactionnelle (toutes les tables sont cohérentes ou aucune)
    # On passe par kb.connect() qui charge vss : requis pour écrire dans `chunks`
    # dont l'index HNSW ne peut être modifié sans l'extension vss chargée.
    print("Inserting into database...")
    file_name = os.path.basename(args.file_path)
    conn = kb.connect("knowledge.duckdb")
    try:
        conn.begin()
        conn.execute(
            "INSERT INTO documents (id, file_name, file_path, category) VALUES (?, ?, ?, ?)",
            (doc_id, file_name, args.file_path, args.category),
        )
        conn.execute(
            "INSERT INTO document_content (document_id, raw_text, embedding) VALUES (?, ?, ?)",
            (doc_id, text, embedding),
        )
        # keywords inséré comme liste native DuckDB (colonne VARCHAR[])
        conn.execute(
            "INSERT INTO document_ai_metadata (document_id, summary, keywords) VALUES (?, ?, ?)",
            (doc_id, analysis.summary, analysis.keywords),
        )
        # Chunks : partie intégrante du schéma courant. Si l'insertion échoue
        # (table absente = base non migrée), on rollback TOUT pour garder la
        # base cohérente (un doc a soit ses chunks soit rien, jamais un doc
        # orphelin sans chunks qui serait silencieusement incomplet).
        if chunk_rows:
            conn.executemany(
                """INSERT INTO chunks
                   (id, document_id, chunk_index, text, element_type,
                    page_number, section, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                chunk_rows,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        print("Error: insertion transaction failed, rolled back.")
        raise
    finally:
        conn.close()

    print(f"Hash: {doc_id}")
    print("SUCCESS")


def _purge_document(doc_id: str) -> None:
    """Supprime un document et toutes ses dépendances (chunks, contenu, metadata).

    Utilisé lors de la mise à jour d'un document modifié : on purge l'ancienne
    version (identifiée par file_path) avant de ré-ingérer la nouvelle.
    Charge vss (via kb.connect) pour pouvoir supprimer dans la table chunks
    indexée HNSW.

    NB : pas de transaction explicite (begin/commit). DuckDB vérifie les FK de
    façon immédiate dans une transaction, ce qui ferait échouer le DELETE du
    parent. En autocommit (enfant→parent), la suppression fonctionne.
    """
    conn = kb.connect("knowledge.duckdb")
    try:
        try:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        except duckdb.CatalogException:
            # Table chunks absente (vieille base non migrée) : on ignore ce
            # DELETE mais on laisse remonter toute autre erreur DB (connexion,
            # contrainte, etc.) qui ne doit pas être masquée silencieusement.
            pass
        conn.execute("DELETE FROM document_content WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM document_ai_metadata WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
