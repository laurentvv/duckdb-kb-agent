"""Utilitaires partagés de la base de connaissances (skills).

Centralise : troncature de texte, appel embeddings Ollama (bge-m3),
connexion DuckDB avec chargement des extensions (FTS + vss).

Importable depuis les skills car le cwd à l'exécution est la racine du projet.
"""

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
