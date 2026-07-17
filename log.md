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
