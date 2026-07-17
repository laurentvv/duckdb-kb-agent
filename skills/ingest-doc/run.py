import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import duckdb
import fitz  # PyMuPDF
import docx
import pandas as pd
from pydantic import BaseModel
from openai import OpenAI

# Lib partagée (cwd = racine du projet à l'exécution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import kb  # noqa: E402

class DocAnalysis(BaseModel):
    summary: str
    keywords: list[str]

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    elif ext == '.docx':
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    elif ext == '.csv':
        df = pd.read_csv(file_path)
        return df.to_string()
    elif ext == '.xlsx':
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
    args = parser.parse_args()

    if not os.path.exists(args.file_path):
        print(f"File not found: {args.file_path}")
        return

    # 1. Hash d'abord (lecture binaire, rapide)
    print("Generating hash...")
    doc_id = get_hash(args.file_path)

    # 2. Vérification de doublon AVANT l'extraction/l'analyse LLM (coûteuses)
    conn = duckdb.connect("knowledge.duckdb")
    try:
        res = conn.execute(
            "SELECT id FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
    finally:
        conn.close()
    if res:
        print(f"Document already ingested with hash {doc_id}")
        return

    # 3. Extraction du texte
    print(f"Extracting text from {args.file_path}...")
    try:
        text = extract_text(args.file_path)
    except Exception as e:
        print(f"Error extracting text: {e}")
        return

    # 4. Analyse LLM
    print("Analyzing text with LLM...")
    analysis = analyze_text(text)

    # 5. Embedding vectoriel (non bloquant : None si Ollama indisponible)
    print("Computating embedding (bge-m3)...")
    embedding = kb.embed(kb.truncate(text))
    if embedding is None:
        print("Warning: embedding échoué (Ollama/bge-m3 down ?) -> doc ingéré sans vecteur.")

    # 6. Insertion transactionnelle (les 3 tables sont cohérentes ou aucune)
    print("Inserting into database...")
    file_name = os.path.basename(args.file_path)
    conn = duckdb.connect("knowledge.duckdb")
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
        conn.commit()
    except Exception:
        conn.rollback()
        print("Error: insertion transaction failed, rolled back.")
        raise
    finally:
        conn.close()

    print(f"Hash: {doc_id}")
    print("SUCCESS")

if __name__ == "__main__":
    main()
