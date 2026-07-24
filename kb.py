"""Utilitaires partagés de la base de connaissances (skills).

Centralise : troncature de texte, appel embeddings Ollama (bge-m3),
connexion DuckDB avec chargement des extensions (FTS + vss).

Importable depuis les skills car le cwd à l'exécution est la racine du projet.
"""

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Optional

import duckdb

DB_PATH = "knowledge.duckdb"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("KB_EMBED_MODEL", "bge-m3:latest")
EMBED_DIM = 1024

# --- Vision LLM (OCR/description des images : PDF scannés, images DOCX, .png) ---
# Opt-in (défaut off) car un appel VLM = ~15-30s/image. Active avec
# KB_VISION_ENABLED=1 ou --vision (CLI ingest-doc). Réutilise le MÊME modèle que
# le chat (Gemma 4 E4B est multimodal) -> aucun modèle supplémentaire à puller.
# Format OpenAI-compatible (suffixe /v1) pour le client openai.OpenAI.
LLM_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/v1"
VISION_MODEL = os.getenv("KB_VISION_MODEL",
                         "hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL")
VISION_ENABLED = os.getenv("KB_VISION_ENABLED", "").lower() in ("1", "true", "yes")
VISION_TIMEOUT = int(os.getenv("KB_VISION_TIMEOUT", "300"))  # s (vs 60 dur dans pdf-ocr-ai)
VISION_DPI = int(os.getenv("KB_VISION_DPI", "200"))          # rasterisation pages (compromis perf)
MAX_TEXT_CHARS = 8000  # bge-m3 limite ~8192 tokens ; troncature par défaut.
                       # En cas d'erreur de contexte (français technique gourmand
                       # en tokens), kb.embed réduit progressivement la taille.

# Paramètres de la fusion RRF
RRF_K = 60           # constante standard du Reciprocal Rank Fusion
SEARCH_POOL = 20     # nb de candidats récupérés par chaque moteur avant fusion
# Bonus accordé aux meilleurs rangs FTS : un top-1 FTS est un signal fort de
# match exact (URL, commande, numéro) qu'il faut préserver face au vectoriel,
# qui peut ramener des docs sémantiquement proches mais sans le terme exact.
RRF_FTS_TOP_WEIGHTS = (3.0, 2.0)   # multiplicateurs pour rang FTS 0 et 1
RRF_VECTOR_WEIGHT = 1.5           # poids du vote vectoriel (synonymes/intention)
RRF_FTS_VALIDATE_TOP = 8          # un doc FTS top-rang ne reçoit le bonus QUE s'il
                                  # figure aussi dans ce top-K vectoriel (validation
                                  # croisée). Évite de booster un doc lexicalement
                                  # proche mais sémantiquement hors-sujet (ex. RDS
                                  # pour une requête "Sage 100").


def connect(db_path: str = DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB avec FTS + vss chargés (best-effort pour vss)."""
    con = duckdb.connect(db_path, read_only=read_only)
    con.execute("LOAD fts;")
    try:
        con.execute("LOAD vss;")
        try:
            con.execute("SET hnsw_enable_experimental_persistence = true;")
        except Exception:
            pass
    except Exception:
        # vss indisponible : la recherche vectorielle sera désactivée,
        # mais la FTS continue de fonctionner.
        pass
    return con


def truncate(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Tronque le texte à `limit` caractères (limite safe pour bge-m3)."""
    return (text or "")[:limit]


def get_chunk_id(doc_id: str, chunk_index: int) -> str:
    """ID déterministe d'un chunk = sha256(doc_id + ':' + chunk_index).

    Centralisé ici pour garantir un hash cohérent entre tous les scripts
    (ingest-doc, batch_ingest, rechunk) — sinon une divergence casserait les
    jointures chunks <-> document.
    """
    return hashlib.sha256(f"{doc_id}:{chunk_index}".encode("utf-8")).hexdigest()[:64]


def embed(text: str, model: str = EMBED_MODEL) -> Optional[list[float]]:
    """Calcule l'embedding via Ollama. Renvoie None si l'appel échoue.

    En cas d'erreur de contexte (texte trop long pour bge-m3), réessaie avec
    une troncature progressivement réduite (8000 -> 4000 -> 2000 car.).
    """
    # Tailles essayées, de la plus grande à la plus petite. Le français se
    # tokenize en plus de tokens que l'anglais, d'où la réduction progressive.
    for limit in (MAX_TEXT_CHARS, 4000, 2000):
        payload = json.dumps({"model": model, "prompt": truncate(text, limit)}).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vec = data.get("embedding")
            if vec and len(vec) == EMBED_DIM:
                return vec
            return None  # erreur applicative non récupérable
        except urllib.error.HTTPError as e:
            # 500 "exceeds context length" -> on réessaie plus court
            if e.code == 500 and "context length" in (e.read().decode("utf-8", "ignore")):
                continue
            return None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------- Recherche

def search_fts(con, query: str, pool: int = SEARCH_POOL) -> list[dict]:
    """Recherche BM25 (FTS). Renvoie une liste de dicts {document_id, score, rank}."""
    try:
        rows = con.execute(
            f"""
            SELECT c.document_id,
                   fts_main_document_content.match_bm25(c.document_id, ?) AS score
            FROM document_content c
            WHERE fts_main_document_content.match_bm25(c.document_id, ?) IS NOT NULL
            ORDER BY score DESC LIMIT {int(pool)}
            """,
            [query, query],
        ).fetchall()
    except Exception:
        return []
    return [{"document_id": r[0], "score": float(r[1]), "rank": i}
            for i, r in enumerate(rows)]


def search_vector(con, query: str, pool: int = SEARCH_POOL,
                  model: str = EMBED_MODEL) -> list[dict]:
    """Recherche vectorielle (cosine via index HNSW). [] si embeddings indisponibles."""
    qvec = embed(query, model=model)
    if qvec is None:
        return []
    try:
        # <=> = cosine distance (0=identique). On ne considère que les docs embeddés.
        rows = con.execute(
            f"""
            SELECT document_id, embedding <=> ? AS distance
            FROM document_content
            WHERE embedding IS NOT NULL
            ORDER BY distance ASC LIMIT {int(pool)}
            """,
            [qvec],
        ).fetchall()
    except Exception:
        return []
    # distance -> score similaire (1 - distance), pour info
    return [{"document_id": r[0], "score": 1.0 - float(r[1]), "rank": i}
            for i, r in enumerate(rows)]


def hybrid_search(con, query: str, k: int = 3,
                  mode: str = "hybrid", model: str = EMBED_MODEL) -> list[dict]:
    """Recherche hybride FTS + vectorielle avec fusion RRF.

    mode: 'hybrid' | 'fts' | 'vector'
    Renvoie top-k dicts avec : document_id, file_name, raw_text, summary,
    score (RRF si hybride), source ('fts'/'vector'/'both').
    """
    fts_hits = search_fts(con, query) if mode in ("hybrid", "fts") else []
    vec_hits = search_vector(con, query, model=model) if mode in ("hybrid", "vector") else []

    if mode == "fts":
        ranked_ids = [h["document_id"] for h in fts_hits]
        source_of = {h["document_id"]: "fts" for h in fts_hits}
        score_of = {h["document_id"]: h["score"] for h in fts_hits}
    elif mode == "vector":
        ranked_ids = [h["document_id"] for h in vec_hits]
        source_of = {h["document_id"]: "vector" for h in vec_hits}
        score_of = {h["document_id"]: h["score"] for h in vec_hits}
    else:
        # Fusion Reciprocal Rank Fusion :
        #  - bonus sur les top-rangs FTS (signaux de match exact type URL/commande),
        #    MAIS uniquement si le doc est aussi dans le pool vectoriel (validation
        #    croisée). Cela évite de sur-pondérer un doc lexicalement proche mais
        #    sémantiquement hors-sujet (ex. "RDS" pour une requête "Sage 100").
        #  - vectoriel légèrement pondéré pour capter synonymes et intention.
        vec_ids = {h["document_id"] for h in vec_hits}
        # Top-K vectoriel resserré pour la validation croisée du bonus FTS.
        vec_top_ids = {h["document_id"] for h in vec_hits[:RRF_FTS_VALIDATE_TOP]}
        rrf = {}
        src = {}
        for h in fts_hits:
            mult = 1.0
            if h["rank"] < len(RRF_FTS_TOP_WEIGHTS) and h["document_id"] in vec_top_ids:
                mult = RRF_FTS_TOP_WEIGHTS[h["rank"]]
            rrf[h["document_id"]] = rrf.get(h["document_id"], 0.0) + mult / (RRF_K + h["rank"] + 1)
            src[h["document_id"]] = "fts"
        for h in vec_hits:
            rrf[h["document_id"]] = rrf.get(h["document_id"], 0.0) + RRF_VECTOR_WEIGHT / (RRF_K + h["rank"] + 1)
            src[h["document_id"]] = "both" if h["document_id"] in src else "vector"
        ranked_ids = sorted(rrf, key=lambda d: rrf[d], reverse=True)
        source_of = src
        score_of = rrf

    if not ranked_ids:
        return []

    top_ids = ranked_ids[:k]
    # Récupérer les métadonnées (file_name, raw_text, summary) pour le top-k.
    placeholders = ",".join("?" * len(top_ids))
    rows = con.execute(
        f"""
        SELECT d.id, d.file_name, d.file_path, c.raw_text, m.summary
        FROM documents d
        JOIN document_content c ON d.id = c.document_id
        LEFT JOIN document_ai_metadata m ON d.id = m.document_id
        WHERE d.id IN ({placeholders})
        """,
        top_ids,
    ).fetchall()
    meta = {r[0]: r for r in rows}

    results = []
    for did in top_ids:
        m = meta.get(did)
        if not m:
            continue
        results.append({
            "document_id": did,
            "file_name": m[1],
            "file_path": m[2],
            "raw_text": m[3],
            "summary": m[4],
            "score": score_of.get(did, 0.0),
            "source": source_of.get(did, "?"),
        })
    return results


# ---------------------------------------------------- Recherche niveau "chunks"


def search_fts_chunks(con, query: str, pool: int = SEARCH_POOL) -> list[dict]:
    """Recherche BM25 (FTS) sur la table chunks. Renvoie des dicts {chunk_id,
    document_id, score, rank}."""
    try:
        rows = con.execute(
            f"""
            SELECT c.id, c.document_id,
                   fts_main_chunks.match_bm25(c.id, ?) AS score
            FROM chunks c
            WHERE fts_main_chunks.match_bm25(c.id, ?) IS NOT NULL
            ORDER BY score DESC LIMIT {int(pool)}
            """,
            [query, query],
        ).fetchall()
    except Exception:
        return []
    return [{"chunk_id": r[0], "document_id": r[1], "score": float(r[2]), "rank": i}
            for i, r in enumerate(rows)]


def search_vector_chunks(con, query: str, pool: int = SEARCH_POOL,
                         model: str = EMBED_MODEL) -> list[dict]:
    """Recherche vectorielle (cosine via HNSW) sur chunks.embedding.
    Renvoie des dicts {chunk_id, document_id, score, rank}."""
    qvec = embed(query, model=model)
    if qvec is None:
        return []
    try:
        rows = con.execute(
            f"""
            SELECT id, document_id, embedding <=> ? AS distance
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY distance ASC LIMIT {int(pool)}
            """,
            [qvec],
        ).fetchall()
    except Exception:
        return []
    return [{"chunk_id": r[0], "document_id": r[1],
             "score": 1.0 - float(r[2]), "rank": i}
            for i, r in enumerate(rows)]


def hybrid_search_chunks(con, query: str, k: int = 5,
                         mode: str = "hybrid", model: str = EMBED_MODEL,
                         max_chunks_per_doc: int = 2) -> list[dict]:
    """Recherche hybride au niveau chunk, avec regroupement par document.

    Pipeline :
      1. FTS + vectoriel sur les chunks (pool de SEARCH_POOL candidats chacun).
      2. Fusion RRF (mêmes poids que hybrid_search au niveau document).
      3. Regroupement par document : on garde au plus ``max_chunks_per_doc``
         chunks par document pour diversifier les sources.
      4. Renvoie les ``k`` meilleurs chunks avec leurs métadonnées de structure
         (page_number, section, element_type) + file_name + summary du document.

    Renvoie des dicts avec : chunk_id, document_id, text, element_type,
    page_number, section, file_name, file_path, summary, score, source.
    """
    fts_hits = search_fts_chunks(con, query) if mode in ("hybrid", "fts") else []
    vec_hits = search_vector_chunks(con, query, model=model) if mode in ("hybrid", "vector") else []

    if mode == "fts":
        ranked = fts_hits
        source_of = {h["chunk_id"]: "fts" for h in fts_hits}
        score_of = {h["chunk_id"]: h["score"] for h in fts_hits}
    elif mode == "vector":
        ranked = vec_hits
        source_of = {h["chunk_id"]: "vector" for h in vec_hits}
        score_of = {h["chunk_id"]: h["score"] for h in vec_hits}
    else:
        vec_top_ids = {h["chunk_id"] for h in vec_hits[:RRF_FTS_VALIDATE_TOP]}
        rrf = {}
        src = {}
        for h in fts_hits:
            mult = 1.0
            if h["rank"] < len(RRF_FTS_TOP_WEIGHTS) and h["chunk_id"] in vec_top_ids:
                mult = RRF_FTS_TOP_WEIGHTS[h["rank"]]
            rrf[h["chunk_id"]] = rrf.get(h["chunk_id"], 0.0) + mult / (RRF_K + h["rank"] + 1)
            src[h["chunk_id"]] = "fts"
        for h in vec_hits:
            rrf[h["chunk_id"]] = rrf.get(h["chunk_id"], 0.0) + RRF_VECTOR_WEIGHT / (RRF_K + h["rank"] + 1)
            src[h["chunk_id"]] = "both" if h["chunk_id"] in src else "vector"
        # Map chunk_id -> document_id pour éviter N requêtes _doc_id_of_chunk.
        chunk_doc = {h["chunk_id"]: h.get("document_id") for h in fts_hits + vec_hits}
        ranked_ids = sorted(rrf, key=lambda c: rrf[c], reverse=True)
        ranked = [{"chunk_id": c, "score": rrf[c], "document_id": chunk_doc.get(c)}
                  for c in ranked_ids]
        source_of = src
        score_of = rrf

    if not ranked:
        return []

    # Regroupement par document : au plus max_chunks_par_doc.
    doc_counts: dict[str, int] = {}
    selected: list[dict] = []
    for h in ranked:
        doc_id = h.get("document_id") or _doc_id_of_chunk(con, h["chunk_id"])
        if doc_id is None:
            continue
        if doc_counts.get(doc_id, 0) >= max_chunks_per_doc:
            continue
        doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
        h["document_id"] = doc_id
        selected.append(h)
        if len(selected) >= k:
            break

    if not selected:
        return []

    chunk_ids = [h["chunk_id"] for h in selected]
    placeholders = ",".join("?" * len(chunk_ids))
    rows = con.execute(
        f"""
        SELECT c.id, c.document_id, c.chunk_index, c.text, c.element_type,
               c.page_number, c.section, d.file_name, d.file_path, m.summary
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        LEFT JOIN document_ai_metadata m ON c.document_id = m.document_id
        WHERE c.id IN ({placeholders})
        """,
        chunk_ids,
    ).fetchall()
    meta = {r[0]: r for r in rows}

    results = []
    for h in selected:
        m = meta.get(h["chunk_id"])
        if not m:
            continue
        results.append({
            "chunk_id": h["chunk_id"],
            "document_id": m[1],
            "chunk_index": m[2],
            "text": m[3],
            "element_type": m[4],
            "page_number": m[5],
            "section": m[6],
            "file_name": m[7],
            "file_path": m[8],
            "summary": m[9],
            "score": score_of.get(h["chunk_id"], h.get("score", 0.0)),
            "source": source_of.get(h["chunk_id"], "?"),
        })
    return results


def _doc_id_of_chunk(con, chunk_id: str) -> str | None:
    """Récupère le document_id d'un chunk (fallback si non fourni dans le hit)."""
    try:
        row = con.execute(
            "SELECT document_id FROM chunks WHERE id = ?", [chunk_id]
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None
