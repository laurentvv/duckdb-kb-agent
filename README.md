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
- **Semantic chunking (Parent-Child)**: documents are split into structure-aware chunks (titles as boundaries, tables preserved, ~600-1200 chars). These "Parent" chunks are then subdivided into smaller "Child" chunks (~300 chars) for maximum embedding precision, while the LLM is fed the entire Parent chunk to retain maximum context.
- **Hybrid retrieval (chunk-level)**: BM25 (exact match) + bge-m3 embeddings (semantic) fused via Reciprocal Rank Fusion, with per-document diversification. Contexts are injected into the LLM prompt using strict XML tags (`<document><source>...</source><content>...</content></document>`) to prevent hallucinations.
- **Verifiable citations**: each result carries page number, section and element type, so the agent can cite its sources.
- **Zero Cloud**: 100% local (Ollama for embeddings + LLM, DuckDB for storage/search). No external API.
- **Agent-First Architecture**: a strict `AGENTS.md` manifesto instructs the AI on how to interact with the database using isolated Python scripts (`skills/`).
- **Modern Stack**: Python 3.14, `uv`, Pydantic, DuckDB (FTS + vss/HNSW).

## 🛠️ Prérequis

- **Python 3.14** et **[uv](https://docs.astral.sh/uv/)**.
- **[Ollama](https://ollama.com/)** démarré en local, avec :
  - un modèle de génération (chat web + analyse à l'ingestion) — configurable via `OLLAMA_BASE_URL` et `OLLAMA_MODEL` ;
  - le modèle d'**embedding** `bge-m3` (`ollama pull bge-m3`) pour la recherche vectorielle (configurable via `KB_EMBED_MODEL`).
  - pour la **vision** (images/PDF scannés, *optionnel*) : un modèle multimodal. Par défaut le même Gemma 4 (qui est multimodal) — aucun modèle supplémentaire à installer.
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

### Vision LLM (images, images embarquées & PDF scannés)

Par défaut, les images (PDF scannés, images embarquées dans les PDF et DOCX, fichiers `.png`/`.jpg` isolés) sont **traitées automatiquement** et envoyées à un modèle multimodal local (Gemma 4, déjà présent — aucun modèle supplémentaire) qui génère une transcription/description indexée comme un chunk normal.

```bash
# Ingestion standard avec vision active par défaut
uv run skills/ingest-doc/run.py "C:\chemin\capture.png"
uv run skills/ingest-doc/run.py "C:\chemin\pdf_scanné.pdf"

# Si besoin de désactiver pour gagner du temps
set KB_VISION_ENABLED=0
uv run batch_ingest.py "C:\chemin\dossier"
```

⚠️ **Coût** : chaque image = ~15-30s d'appel au VLM. La vision est donc **opt-out** (activée par défaut). Si le VLM est indisponible, l'image est skippée silencieusement (l'ingestion ne crash pas).

Configuration (variables d'environnement) :
- `KB_VISION_ENABLED=0` — désactive la vision globalement (par défaut : 1)
- `KB_VISION_MODEL` — modèle multimodal (défaut : le même Gemma 4 que le chat)
- `KB_VISION_DPI` — résolution de rasterisation des pages PDF (défaut : 200)
- `KB_VISION_TIMEOUT` — timeout par image en secondes (défaut : 300)

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
- **Réindexer avec vision** (rendre les captures d'écran/images recherchables) — voir [`docs/REINDEXATION-VISION.md`](docs/REINDEXATION-VISION.md) pour la procédure détaillée :
  ```bash
  uv run skills/reindex-vision/run.py --limit 3                                  # test rapide
  uv run skills/reindex-vision/run.py --filter "file_path ILIKE '%.docx'"        # DOCX seulement
  ```

## 🧪 Tests

```bash
uv run pytest                      # tests unitaires (base temporaire, mock LLM/embedding)
uv run pytest -m integration       # + tests d'intégration (nécessitent knowledge.duckdb)
```

### 💡 Expérimentation Headroom (Refus stratégique)
Une intégration du SDK **Headroom** a été testée et benchmarkée (`bench/run_bench_headroom.py`) pour compresser le contexte RAG en entrée du LLM. 
**Résultat :** Bien que la compression puisse atteindre jusqu'à 90% d'économie de tokens sans dégrader la qualité des réponses (avec prompt strict en français et `target_ratio=0.5`), le coût en latence (~+3 secondes par requête pour charger le modèle ML Kompress localement) dépasse les bénéfices pour une architecture **100% locale** (Zéro Cloud).
**Décision :** Headroom a été retiré du projet car les tokens d'entrée locaux (Ollama) n'ont pas de coût financier direct, et la vitesse de réponse (UX) est prioritaire. Le code et les dépendances ont été purgés pour maintenir le projet léger.

## 🧱 Schéma de la base

```text
documents              id (hash SHA-256 du contenu) PK, file_name, file_path, category, indexed_at
document_content       document_id PK (1:1), raw_text (texte complet), embedding FLOAT[1024]
document_ai_metadata   document_id PK (1:1), summary (LLM), keywords VARCHAR[]
chunks                 id PK, document_id FK, chunk_index, text, parent_text TEXT,
                       element_type, page_number, section, embedding FLOAT[1024]
```

Index : FTS (BM25) sur `document_content.raw_text` et `chunks.text` ; HNSW (cosine) sur `document_content.embedding` et `chunks.embedding`.

## 📂 Architecture

```text
duckdb-kb-agent/
├── AGENTS.md               # Directives de l'agent IA
├── kb.py                   # Lib partagée (connexion DuckDB, embeddings, recherche hybride, get_chunk_id)
├── parsing.py              # Extraction structurée (PDF/DOCX/HTML/XLSX/txt) + chunking sémantique
├── vision.py               # Vision LLM (OCR/description des images via Gemma 4 multimodal)
├── pyproject.toml          # Dépendances (uv)
├── knowledge.duckdb        # Base DuckDB (générée, non versionnée)
├── batch_ingest.py         # Ingestion en masse (depuis un chemin fourni)
├── skills/                 # Outils de l'agent
│   ├── init-db/            # Création de la base + tables + index FTS + index vectoriel HNSW
│   ├── ingest-doc/         # Extraction + chunking + insertion + embeddings (Ollama)
│   ├── embed-docs/         # Remplissage massif des embeddings (doc + chunks)
│   ├── search-db/          # Recherche hybride chunk-level (FTS + vectoriel, fusion RRF)
│   ├── reindex/            # Reconstruction de l'index FTS
│   ├── reindex-vision/     # Réindexation avec vision LLM (captures d'écran, PDF scannés)
│   └── migrate-db/         # Migration du schéma (non destructive)
├── bench/                  # Benchmark RAG (questions, run, comparatif)
├── docs/                   # Documentation (audit Unstructured, réindexation vision)
├── tests/                  # Suite pytest
└── web/                    # Interface FastAPI (chat)
```
