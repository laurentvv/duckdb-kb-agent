# Activity Log

* **Ingest** : Import en masse des fichiers depuis 'Modes Opératoires' (hors _Archives).
* **2026-07-16 — Refactor** : revue de code complète.
  - `.gitignore` créé (BDD, `.venv`, `raw/`, caches) ; `pyproject.toml` complété (description réelle, dev-dépendances pytest).
  - Bugs runtime corrigés : clause `WHERE` sur alias `score` + `LOAD fts` manquant dans `web/app.py` ; fermeture de toutes les connexions DuckDB ; ingestion transactionnelle + check de doublon déplacé en amont.
  - Ingestion désormais sur **Ollama local** (cohérent avec le reste), modèle configurable (`OLLAMA_*`).
  - Schéma SQL : `PRIMARY KEY` sur `document_id` et `keywords` en `VARCHAR[]`. Base existante (237 docs) migrée via le nouveau skill `skills/migrate-db` (backup conservé).
  - Nouveaux skills : `skills/migrate-db` (migration non destructive, dry-run par défaut), `skills/reindex` (reconstruction FTS robuste).
  - `batch_ingest.py` : chemin source externalisé en argument CLI + `--extensions`.
  - Encodage robuste (UTF-8 → cp1252 → replace) dans `ingest-doc`.
  - Suite de tests **pytest** (20 tests : `extract_text`, `get_hash`, `analyze_text`, `init-db`, `migrate-db`, recherche e2e). Scripts de debug jetables supprimés.
* **2026-07-17 — Recherche hybride (FTS + vectorielle)** :
  - Ajout d'une colonne `embedding FLOAT[1024]` + index **HNSW** (cosine) sur `document_content` (extension DuckDB `vss`, persistance expérimentale activée). Migration non destructive appliquée à la base existante.
  - Nouveau skill `skills/embed-docs` : remplissage massif des embeddings via **bge-m3** (Ollama), troncature à 8000 car., reprise sécurisée, options `--filter`/`--limit`/`--rebuild`.
  - `ingest-doc` calcule désormais l'embedding à l'ingestion (non bloquant si Ollama down).
  - Refonte de la recherche en mode **hybride** : fusion FTS (BM25) + vectoriel (cosine) par **Reciprocal Rank Fusion**. `skills/search-db` et `web/app.py` basculent sur l'hybride ; `--mode fts|vector|hybrid` pour isoler chaque moteur.
  - Lib partagée `kb.py` (connexion, embeddings, recherche). Validation sur banc Sage : l'embedding désambiguïse Sage 100 vs Sage 1000 (vector top-1 = Sage 100 vs FTS top-1 = Sage 1000) et l'hybride élimine le bruit hors-thème.
  - Tests pytest étendus (fusion RRF, embed-docs, init-db + HNSW).
* **2026-07-18 — Tuning RRF + indexation totale** :
  - **Tuning de la fusion hybride** : introduction d'un bonus sur les top-rangs FTS (×3 pour r0, ×2 pour r1) avec **validation croisée vectorielle** (le bonus ne s'applique que si le doc figure aussi dans le top-8 vectoriel). Objectif : préserver les matchs exacts (URL `192.168…`, commandes `Netdom`) tout en éliminant le bruit lexical hors-thème (ex. doc RDS pour une requête « Sage 100 »). Résultat : 8/9 requêtes top-1 correctes ; le cas « Sage 100 vs Sage 1000 » reste un ex-aequo irréductible (le 1000 est légitime lexicalement et sémantiquement).
  - **Indexation totale depuis zéro** : reindex FTS + rebuild complet des 232 embeddings (0 échec). Base dans un état propre et certifié.
  - **Bugs DuckDB résolus** : (1) `stopwords has been deleted` — le FTS ne supporte pas drop+create dans la même session (skill `reindex` utilise 2 connexions) ; (2) `CHECKPOINT` échoue si `vss` n'est pas chargé (`HNSW` non-bindé) → `kb.connect()` charge désormais toujours `vss` ; (3) `hnsw_enable_experimental_persistence` requis pour persister l'index HNSW sur disque.
  - **Nettoyage** : 3 backups `.duckdb` obsolètes supprimés (16 Mo), `.gitignore` étendu (`.agents/`, `.zcode/`).
  - 32/32 tests pytest verts.
* **2026-07-18 — Suppression du dossier `raw/`** :
  - L'ingestion se fait désormais depuis **n'importe quel chemin fourni par l'utilisateur** (fichier ou dossier local/réseau/UNC), plus de convention de dossier `raw/` imposée.
  - Dossier `raw/` physique supprimé ; doc de test `raw/test.txt` retiré de la base (DELETE, 236 docs restants).
  - `.gitignore` : section `raw/` remplacée par un commentaire générique (l'utilisateur ajoute ses chemins si besoin).
  - `AGENTS.md` §1 reformulé : règle d'or générique sur les fichiers sources (peu importe le chemin, on ne modifie jamais, on indexe via le skill en lecture seule).
  - `README.md`, `batch_ingest.py` : exemples mis à jour avec des chemins Windows (`C:\chemin\...`) au lieu de `raw/`.
  - Document de conception obsolète `duckdb-kb-agent-plan.md` supprimé (décrivait l'ancienne architecture avec `raw/`).
* **2026-07-24 — Pipeline de chunking + extraction structurée** :
  - **Objectif** : améliorer la qualité du retrieval (la baseline FTS tronquait l'embedding à 8000 car. et perdait tableaux/structure).
  - **Extraction structurée** (`parsing.py`, nouveau module) : routeur par extension — PDF (pdfplumber, tables extraites + n° de page), DOCX (**python-docx** en principal, mammoth en repli ; headings + tables + listes), HTML (trafilatura), XLSX/CSV, texte/Markdown. Renvoie des éléments typés (Title/NarrativeText/Table/ListItem) avec page_number et section courante.
  - **Chunking sémantique** (`parsing.chunk_elements`) : regroupement en chunks cohérents (~600-1200 car.) respectant la structure (titre = frontière si chunk ≥ 400 car. ; table = chunk dédié ; découpage par phrases avec overlap sur les longs éléments). Plafond anti-explosion de 100 chunks/doc.
  - **Schéma** : nouvelle table `chunks` (id, document_id, chunk_index, text, element_type, page_number, section, embedding FLOAT[1024]) + index FTS sur `chunks.text` + index HNSW sur `chunks.embedding`. Création dans `init-db` + migration non destructive dans `migrate-db`.
  - **Retrieval chunk-level** (`kb.py`) : `search_fts_chunks`, `search_vector_chunks`, `hybrid_search_chunks` (RRF + regroupement par document, diversification max 2 chunks/doc). `web/app.py` et `search-db` basculent sur le niveau chunk (repli document-level si pas de chunks). Citations vérifiables (page/section/type).
  - **Dédoublonnage intelligent** : skip si contenu identique, **mise à jour** (purge ancienne version + chunks) si document modifié, `--force` pour forcer. Correction d'un bug de contrainte FK au DELETE (purge en autocommit enfant→parent, DuckDB vérifie les FK immédiatement en transaction).
  - **Bugs corrigés en cours de route** : (1) chunking trop agressif (micro-chunks sur docs titrés) → `section_min_chars=400` ; (2) mammoth perdait du contenu (VUP_WCF) → python-docx principal ; (3) `ingest-doc` crashait si vss non chargé → `kb.connect()` + LOAD vss sécurisé ; (4) document monstrueux (France Billet 6841 chunks) → plafond 100/doc.
  - **Benchmark** : 254 docs, 1429 chunks (830 NarrativeText, 400 Title, 174 Table, 25 ListItem), 254/254 résumés LLM. Sur 20 questions : **qualité équivalente à la baseline 9.9/10**, **latence -52%** (13.5s vs 28.0s), citations source disponibles.
  - **Code review + corrections** : propagation document_id dans la fusion RRF (perf), current_top glissant (PDF lignes), section CSV = basename, LOAD vss dans try/except, cohérence transactionnelle chunks, `get_chunk_id` centralisé dans kb.py, imports paresseux, `include_tables=True`.
  - **Tests** : 54 tests pytest verts (parsing, chunking, retrieval chunks, extraction binaire/CSV).
  - **Doc** : README + AGENTS.md mis à jour (pipeline chunks, schéma, dédoublonnage intelligent, embeddings chunk-level). Audit Unstructured-IO archivé dans `docs/audit-unstructured.md`.
  - **Audit** (`docs/audit-unstructured.md`) : évaluation de la lib Unstructured-IO pour le parsing. Conclusion : stack léger (pdfplumber/mammoth/trafilatura) retenu, plus adapté au contexte local Windows que Unstructured `hi_res` (torch exclu de Windows).
