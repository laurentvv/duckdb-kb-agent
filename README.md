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

    The agent uses specialized Python skills to ingest raw documents (PDF, Word, Excel), extracts metadata and summaries using LLMs (Local or API), and stores everything in a **DuckDB database**. It answers
  user queries instantly using DuckDB's native **Full-Text Search (FTS)**, completely bypassing the need for complex and costly Vector Databases (RAG).

### ✨ Key Features
- **Zero Hallucination**: The Agent queries the SQL database and bases its answers purely on the raw FTS extracts.
- **RAG Alternative**: No embeddings, no vector DBs. Uses BM25 Full-Text Search for ultra-fast, exact-match document retrieval.
- **Agent-First Architecture**: Features a strict `AGENTS.md` manifesto instructing the AI on how to interact with the database using isolated Python scripts (`skills/`).
- **Modern Stack**: Built with Python 3.14, `uv`, Pydantic (Structured Output), and PyMuPDF.

## 🛠️ Prérequis

- **Python 3.14** et **[uv](https://docs.astral.sh/uv/)**.
- **[Ollama](https://ollama.com/)** démarré en local, avec :
  - un modèle de génération (chat web + analyse à l'ingestion) — configurable via `OLLAMA_BASE_URL` et `OLLAMA_MODEL` ;
  - le modèle d'**embedding** `bge-m3` (`ollama pull bge-m3`) pour la recherche vectorielle (configurable via `KB_EMBED_MODEL`).
- Les documents sources sont placés dans `raw/` (non versionné).

## 🚀 Démarrage

```bash
# 1. Installer les dépendances
uv sync

# 2. Initialiser la base DuckDB (tables + index FTS + index vectoriel HNSW)
uv run skills/init-db/run.py

# 3. Ingestion d'un document (embedding calculé automatiquement)
uv run skills/ingest-doc/run.py "raw/mon-document.pdf" --category "Tech"

# 4. Recherche hybride (FTS + vectoriel, fusion RRF) — par défaut
uv run skills/search-db/run.py "mots clés" --limit 3
#    modes isolables : --mode fts | vector | hybrid
```

### Ingestion en masse

```bash
uv run batch_ingest.py "./raw/dossier" --category "Exploitation"
# Filtrer par extensions :
uv run batch_ingest.py "./raw/dossier" --extensions .pdf .docx
```

### Interface web (chat)

```bash
uv run uvicorn web.app:app --reload
```

## 🔧 Maintenance

- **Reconstruire l'index FTS** (après des ingestions massives ou résultats incohérents) :
  ```bash
  uv run skills/reindex/run.py
  ```
- **(Re)calculer les embeddings** (recherche vectorielle) — reprise sécurisée :
  ```bash
  uv run skills/embed-docs/run.py                       # docs sans embedding
  uv run skills/embed-docs/run.py --rebuild             # recalculer tout
  uv run skills/embed-docs/run.py --filter "file_path ILIKE '%\\sage\\%'"   # sous-ensemble
  ```
- **Migrer une base ancienne** vers le schéma courant (clés primaires, `keywords` en liste, colonne `embedding` + index HNSW) :
  ```bash
  uv run skills/migrate-db/run.py            # dry-run (lecture seule)
  uv run skills/migrate-db/run.py --apply    # exécute (sauvegarde automatique)
  ```

## 🧪 Tests

```bash
uv run pytest                      # tests unitaires (base temporaire, mock LLM/embedding)
uv run pytest -m integration       # + tests d'intégration (nécessitent knowledge.duckdb)
```

## 📂 Architecture

```text
duckdb-kb-agent/
├── AGENTS.md               # Directives de l'agent IA
├── kb.py                   # Lib partagée (connexion DuckDB, embeddings, recherche hybride)
├── pyproject.toml          # Dépendances (uv)
├── knowledge.duckdb        # Base DuckDB (générée, non versionnée)
├── log.md                  # Journal d'activité
├── batch_ingest.py         # Ingestion en masse
├── raw/                    # Documents sources (immuable, non versionné)
├── skills/                 # Outils de l'agent
│   ├── init-db/            # Création de la base + index FTS + index vectoriel HNSW
│   ├── ingest-doc/         # Extraction + insertion + embedding (Ollama)
│   ├── embed-docs/         # Remplissage massif des embeddings (bge-m3)
│   ├── search-db/          # Recherche hybride (FTS + vectoriel, fusion RRF)
│   ├── reindex/            # Reconstruction de l'index FTS
│   └── migrate-db/         # Migration du schéma (non destructive)
├── tests/                  # Suite pytest
└── web/                    # Interface FastAPI (chat)
```
