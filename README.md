<div align="center">
      <h1>🦆 DuckDB KB Agent</h1>
      <p><b>Agentic Knowledge Base & Document Management System</b></p>
      <p>
        <img src="https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white" alt="Python 3.14" />
        <img src="https://img.shields.io/badge/Package_Manager-uv-purple" alt="uv" />
        <img src="https://img.shields.io/badge/Database-DuckDB-yellow?logo=duckdb" alt="DuckDB" />
        <img src="https://img.shields.io/badge/Architecture-Agentic-success" alt="Agentic Architecture" />
      </p>
    </div>

    ## 💡 About
**DuckDB KB Agent** is a paradigm shift from traditional Markdown-based wikis. Instead of human-maintained documentation, this system is designed to be **operated entirely by an AI Coding Agent** (e.g.,
  Antigravity, Cline).

  The agent uses specialized Python skills to ingest raw documents (PDF, Word, Excel, HTML), extract **structured elements** (titles, paragraphs, tables) with metadata (page number, section, element type), chunk them semantically, and store everything in a **DuckDB database**. It answers user queries using a **hybrid retrieval** (BM25 Full-Text Search + vector embeddings via Reciprocal Rank Fusion) at the **chunk level**, with verifiable source citations.

### ✨ Key Features
- **Structured extraction**: PDF (pdfplumber, tables + page numbers), Word (python-docx, tables + headings), HTML (trafilatura), Office/Excel — all routed automatically.
- **Semantic chunking**: documents are split into structure-aware chunks (titles as boundaries, tables preserved, ~600-1200 chars) so every passage is vectorized and retrievable.
- **Hybrid retrieval (chunk-level)**: BM25 (exact match) + bge-m3 embeddings (semantic) fused via Reciprocal Rank Fusion, with per-document diversification.
- **Verifiable citations**: each result carries page number, section and element type, so the agent can cite its sources.
- **Zero Cloud**: 100% local (Ollama for embeddings + LLM, DuckDB for storage/search). No external API.
- **Agent-First Architecture**: a strict `AGENTS.md` manifesto instructs the AI on how to interact with the database using isolated Python scripts (`skills/`).
- **Modern Stack**: Python 3.14, `uv`, Pydantic, DuckDB (FTS + vss/HNSW).

## 🛠️ Prérequis

- **Python 3.14** et **[uv](https://docs.astral.sh/uv/)**.
- **[Ollama](https://ollama.com/)** démarré en local, avec :
  - un modèle de génération (chat web + analyse à l'ingestion) — configurable via `OLLAMA_BASE_URL` et `OLLAMA_MODEL` ;
  - le modèle d'**embedding** `bge-m3` (`ollama pull bge-m3`) pour la recherche vectorielle (configurable via `KB_EMBED_MODEL`).
- Les documents sources : l'utilisateur fournit leur chemin à l'ingestion (fichier ou dossier local/réseau). Aucun dossier `raw/` imposé ; les documents ne sont pas versionnés (voir `.gitignore`).

## 🚀 Démarrage

```bash
# 1. Installer les dépendances
uv sync

# 2. Initialiser la base DuckDB (tables + index FTS + index vectoriel HNSW)
uv run skills/init-db/run.py

# 3. Ingestion d'un document
#    (extraction structurée + chunking + embedding doc + embeddings chunks + résumé LLM)
uv run skills/ingest-doc/run.py "C:\chemin\vers\document.pdf" --category "Tech"

# 4. Recherche hybride (FTS + vectoriel, fusion RRF) — par défaut
uv run skills/search-db/run.py "mots clés" --limit 3
#    modes isolables : --mode fts | vector | hybrid
```

### Ingestion en masse

```bash
uv run batch_ingest.py "C:\chemin\vers\dossier" --category "Exploitation"
# Filtrer par extensions :
uv run batch_ingest.py "C:\chemin\vers\dossier" --extensions .pdf .docx
```

Le dédoublonnage est **intelligent** : un document non modifié (même contenu) est skippé, un document modifié (même chemin, contenu différent) est **mis à jour** (l'ancienne version et ses chunks sont purgés puis remplacés). `--force` force la ré-ingestion.

### Interface web (chat)

```bash
uv run uvicorn web.app:app --reload
```

## 🔧 Maintenance

- **Reconstruire l'index FTS** (après des ingestions massives ou résultats incohérents) :
  ```bash
  uv run skills/reindex/run.py
  ```
- **(Re)calculer les embeddings** (document et/ou chunks) — reprise sécurisée :
  ```bash
  uv run skills/embed-docs/run.py                       # docs/chunks sans embedding
  uv run skills/embed-docs/run.py --rebuild             # recalculer tout
  uv run skills/embed-docs/run.py --chunks-only         # embeddings de chunks uniquement
  uv run skills/embed-docs/run.py --filter "file_path ILIKE '%\\sage\\%'"   # sous-ensemble
  ```
- **Migrer une base ancienne** vers le schéma courant (clés primaires, `keywords` en liste, colonne `embedding` + index HNSW, **table `chunks`** + index FTS/HNSW) :
  ```bash
  uv run skills/migrate-db/run.py            # dry-run (lecture seule)
  uv run skills/migrate-db/run.py --apply    # exécute (sauvegarde automatique)
  ```

## 🧪 Tests

```bash
uv run pytest                      # tests unitaires (base temporaire, mock LLM/embedding)
uv run pytest -m integration       # + tests d'intégration (nécessitent knowledge.duckdb)
```

## 🧱 Schéma de la base

```text
documents              id (hash SHA-256 du contenu) PK, file_name, file_path, category, indexed_at
document_content       document_id PK (1:1), raw_text (texte complet), embedding FLOAT[1024]
document_ai_metadata   document_id PK (1:1), summary (LLM), keywords VARCHAR[]
chunks                 id PK, document_id FK, chunk_index, text, element_type,
                       page_number, section, embedding FLOAT[1024]
```

Index : FTS (BM25) sur `document_content.raw_text` et `chunks.text` ; HNSW (cosine) sur `document_content.embedding` et `chunks.embedding`.

## 📂 Architecture

```text
duckdb-kb-agent/
├── AGENTS.md               # Directives de l'agent IA
├── kb.py                   # Lib partagée (connexion DuckDB, embeddings, recherche hybride, get_chunk_id)
├── parsing.py              # Extraction structurée (PDF/DOCX/HTML/XLSX/txt) + chunking sémantique
├── pyproject.toml          # Dépendances (uv)
├── knowledge.duckdb        # Base DuckDB (générée, non versionnée)
├── batch_ingest.py         # Ingestion en masse (depuis un chemin fourni)
├── skills/                 # Outils de l'agent
│   ├── init-db/            # Création de la base + tables + index FTS + index vectoriel HNSW
│   ├── ingest-doc/         # Extraction + chunking + insertion + embeddings (Ollama)
│   ├── embed-docs/         # Remplissage massif des embeddings (doc + chunks)
│   ├── search-db/          # Recherche hybride chunk-level (FTS + vectoriel, fusion RRF)
│   ├── reindex/            # Reconstruction de l'index FTS
│   └── migrate-db/         # Migration du schéma (non destructive)
├── bench/                  # Benchmark RAG (questions, run, comparatif)
├── tests/                  # Suite pytest
└── web/                    # Interface FastAPI (chat)
```
