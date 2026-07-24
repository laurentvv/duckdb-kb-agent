"""Ingestion massive avec le nouveau pipeline (parsing + chunks + embeddings).

Parcourt le dossier Modes Opératoires (hors _Archives) et ingère chaque fichier
textuel via parsing.extract_elements + chunk_elements + embeddings chunks.

Gère proprement les fichiers binaires non textuels (.exe, .png, .zip, .lnk...)
qui sont skippés. Les erreurs d'extraction sur un fichier sont isolées (le
fichier est skippé, l'ingestion continue).

Usage :
  uv run bench/ingest_all.py
"""

import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import parsing
import kb
import duckdb
from openai import OpenAI
from conftest import load_skill

ingest = load_skill("ingest-doc")

SOURCE = Path(r"C:\Users\lvolff\UP\Kalidea - ExploitationDSI - Documents\Exploitation\Modes Opératoires")
EXCLUDE_DIRS = {"_Archives"}
# Extensions textuelles ingérables ; les autres (.exe, .png, .zip, .lnk, .mp4...) sont skippées.
TEXTUAL_EXTS = {".docx", ".doc", ".pdf", ".txt", ".md", ".sql", ".ini", ".conf",
                ".csv", ".xlsx", ".html", ".htm", ".asc", ".tst", ".url", ".msg"}

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL"

# Résumé LLM activé : le summary est utilisé dans web/app.py pour contextualiser
# les réponses de l'agent, et les keywords sont stockés pour usage futur.
# L'appel LLM est sécurisé par un timeout strict (voir analyze_text_llm).
SKIP_LLM = False


# get_chunk_id est centralisé dans kb.py pour garantir un hash cohérent.
get_chunk_id = kb.get_chunk_id


def analyze_text_llm(text, file_name=""):
    """Résumé + mots-clés via LLM local (best-effort, sécurisé contre le blocage).

    SKIPPABLE : SKIP_LLM=True désactive (summary vide).
    Sécurités anti-blocage :
      - troncature stricte du contenu (MAX_LLM_CHARS) ;
      - timeout court (60s) pour échouer vite ;
      - log avant/après pour tracer où ça bloque.
    """
    if SKIP_LLM:
        return ("", [])
    # Troncature stricte : un contenu trop long fait "thinker" Gemma indéfiniment.
    MAX_LLM_CHARS = 6000
    content = text[:MAX_LLM_CHARS]
    if len(text) > MAX_LLM_CHARS:
        content = content + "\n..."

    import json
    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    system_prompt = (
        "Tu es un analyseur de documents. Résume le texte en français (max 2 phrases) "
        "et extrais 5 mots-clés pertinents. Réponds UNIQUEMENT avec un objet "
        'JSON de la forme {"summary": "...", "keywords": ["...", "..."]}.'
    )
    label = f"[{file_name[:30]}] " if file_name else ""
    print(f"    {label}LLM resume... ({len(content)} car)", flush=True)
    try:
        resp = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": content}],
            temperature=0.2,
            response_format={"type": "json_object"},
            timeout=300,   # généreux : laisse Gemma finir même sur les gros docs
        )
        data = json.loads(resp.choices[0].message.content)
        summary = str(data.get("summary", "")).strip() or "No summary"
        kws = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()] or ["error"]
        print(f"    {label}LLM OK.", flush=True)
        return summary, kws
    except Exception as e:
        print(f"    {label}LLM ECHEC (skip resume): {str(e)[:60]}", flush=True)
        return "No summary available (LLM failed)", ["error", "fallback"]


def _purge_in_conn(con, doc_id):
    """Purge un document et ses dépendances dans la connexion donnée.

    Version "connexion partagée" de _purge_document : utilisée par ingest_one
    qui réutilise la même connexion que main(). Gère l'absence de la table
    chunks (vieille base).

    NB : on n'encadre PAS d'une transaction explicite (begin/commit). DuckDB
    vérifie les contraintes FK de façon immédiate dans une transaction, ce qui
    fait échouer le DELETE du parent même après suppression des enfants. En
    autocommit (chaque statement commit séparément), la suppression enfant→parent
    fonctionne correctement.
    """
    try:
        con.execute("DELETE FROM chunks WHERE document_id = ?", [doc_id])
    except Exception:
        pass  # table chunks absente (vieille base)
    con.execute("DELETE FROM document_content WHERE document_id = ?", [doc_id])
    con.execute("DELETE FROM document_ai_metadata WHERE document_id = ?", [doc_id])
    con.execute("DELETE FROM documents WHERE id = ?", [doc_id])


def ingest_one(file_path, con):
    """Ingère un fichier. Renvoie (status, n_chunks, detail).

    Dédoublonnage :
      - contenu identique (même hash) -> skip ("dup")
      - même file_path mais hash différent (doc modifié) -> purge l'ancienne
        version puis ré-ingère la nouvelle ("updated")
      - nouveau fichier -> insère ("ok")
    """
    import os
    import time as _t
    fp = str(file_path)
    name = os.path.basename(fp)
    _t0 = _t.time()

    def _log(msg):
        print(f"    [{_t.time()-_t0:5.1f}s] {name[:40]}: {msg}", flush=True)

    _log("hash...")
    doc_id = ingest.get_hash(fp)

    # (a) Contenu identique -> skip.
    if con.execute("SELECT id FROM documents WHERE id = ?", [doc_id]).fetchone():
        return ("dup", 0, "")

    ext = file_path.suffix.lower()
    if ext not in TEXTUAL_EXTS:
        return ("skip_binary", 0, ext)

    # (b) Ancienne version par file_path ? (document modifié entre-temps)
    old = con.execute(
        "SELECT id FROM documents WHERE file_path = ?", [fp]
    ).fetchone()
    is_update = bool(old)
    if old:
        _log(f"doc modifié, purge ancienne version {old[0][:10]}...")
        _purge_in_conn(con, old[0])

    # Parsing + chunking
    _log("parsing...")
    try:
        elements = parsing.extract_elements(fp)
        text = parsing.elements_to_text(elements)
        chunks = parsing.chunk_elements(elements)
    except Exception as e:
        return ("parse_error", 0, str(e)[:80])

    if not text.strip():
        return ("empty", 0, "")

    _log(f"parsed: {len(elements)} elem, {len(chunks)} chunks, {len(text)} car")

    # Analyse LLM (best-effort)
    summary, keywords = analyze_text_llm(text, file_name=name)

    # Embeddings (doc + chunks)
    _log("embeddings...")
    doc_emb = kb.embed(kb.truncate(text))
    chunk_rows = []
    embed_ok = 0
    for ch in chunks:
        vec = kb.embed(kb.truncate(ch.text)) if ch.text.strip() else None
        if vec is not None:
            embed_ok += 1
        chunk_rows.append((get_chunk_id(doc_id, ch.chunk_index), doc_id, ch.chunk_index,
                           ch.text, ch.element_type, ch.page_number, ch.section, vec))
    _log(f"embeddings OK: doc={'oui' if doc_emb else 'non'}, chunks={embed_ok}/{len(chunks)}")

    # Insertion transactionnelle
    file_name = os.path.basename(fp)
    con.begin()
    con.execute("INSERT INTO documents (id, file_name, file_path, category) VALUES (?,?,?,?)",
                [doc_id, file_name, fp, "Modes Operatoires"])
    con.execute("INSERT INTO document_content (document_id, raw_text, embedding) VALUES (?,?,?)",
                [doc_id, text, doc_emb])
    con.execute("INSERT INTO document_ai_metadata (document_id, summary, keywords) VALUES (?,?,?)",
                [doc_id, summary, keywords])
    if chunk_rows:
        con.executemany(
            "INSERT INTO chunks (id, document_id, chunk_index, text, element_type, "
            "page_number, section, embedding) VALUES (?,?,?,?,?,?,?,?)",
            chunk_rows,
        )
    con.commit()
    status = "updated" if is_update else "ok"
    return (status, len(chunk_rows), f"{embed_ok}/{len(chunk_rows)} emb")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Ingestion massive (pipeline chunks).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Nombre max de NOUVEAUX docs à traiter (les doublons "
                         "ne comptent pas). Permet de traiter par lots.")
    args = ap.parse_args()

    files = [f for f in SOURCE.rglob("*")
             if f.is_file() and not any(p in EXCLUDE_DIRS for p in f.parts)]
    print(f"{len(files)} fichiers trouvés (hors _Archives).", flush=True)

    con = kb.connect("knowledge.duckdb")
    stats = {"ok": 0, "dup": 0, "skip_binary": 0, "parse_error": 0, "empty": 0}
    total_chunks = 0
    new_done = 0   # compteur de docs réellement traités (hors doublons)
    t0 = time.time()
    try:
        for i, f in enumerate(files, 1):
            try:
                status, n_chunks, detail = ingest_one(f, con)
            except Exception as e:
                status, n_chunks, detail = ("error", 0, str(e)[:100])
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
            stats[status] = stats.get(status, 0) + 1
            total_chunks += n_chunks
            # Un doc "nouvellement traité" = ok/updated/parse_error/empty/error
            # (pas dup/skip_binary qui n'ont pas coûté d'extraction).
            if status in ("ok", "updated", "parse_error", "empty", "error"):
                new_done += 1
            if status in ("ok", "updated"):
                tag = "OK" if status == "ok" else "UPD"
                print(f"  [{i}/{len(files)}] {tag} {f.name[:50]} -> {n_chunks} chunks ({detail})", flush=True)
            elif status in ("parse_error", "error"):
                print(f"  [{i}/{len(files)}] {status.upper()} {f.name[:50]} : {detail}", flush=True)
            elif new_done % 10 == 0 and new_done > 0:
                elapsed = time.time() - t0
                print(f"  [{i}/{len(files)}] ... {new_done} nouveaux ({elapsed:.0f}s) stats: {stats}", flush=True)
            # Arrêt propre si limite atteinte (permet le traitement par lots).
            if args.limit and new_done >= args.limit:
                print(f"  --limit {args.limit} atteint : arrêt propre après {new_done} nouveaux docs.", flush=True)
                break
    finally:
        con.close()

    elapsed = time.time() - t0
    print(f"\n=== Termine en {elapsed:.0f}s ===", flush=True)
    print(f"Stats: {stats}", flush=True)
    print(f"Total chunks inseres: {total_chunks}", flush=True)
    print(f"Nouveaux docs traites: {new_done}", flush=True)


if __name__ == "__main__":
    main()
