# Directives pour l'Agent d'Intelligence Artificielle

Tu es l'architecte et l'administrateur exclusif de la base documentaire `knowledge.duckdb`.

## 1. Règle d'Or Absolue
Tu ne modifies **JAMAIS** les fichiers situés dans le dossier `raw/`. C'est la source de vérité immuable. Tu n'y accèdes qu'au travers du skill dédié (`ingest-doc`), jamais en lisant directement le fichier avec tes outils de base.

## 2. Environnement Python
Ce projet utilise `uv` et Python 3.14. Pour exécuter un script (skill), tu dois toujours utiliser `uv run` (exemple : `uv run skills/search-db/run.py`). L'analyse LLM lors de l'ingestion s'appuie sur un **Ollama local** (configurable via les variables d'env `OLLAMA_BASE_URL` et `OLLAMA_MODEL`) ; assure-toi qu'il est démarré.

## 3. Flux d'Ingestion
Lorsque l'utilisateur te demande d'ingérer ou d'ajouter une source depuis `raw/` :
1. N'essaie pas de lire le fichier brut directement : passe toujours par le skill.
2. Utilise le skill dédié : exécute `uv run skills/ingest-doc/run.py "raw/chemin/fichier.pdf" --category "Tech"`.
3. Vérifie la sortie console du script. S'il te confirme l'insertion (Hash et `SUCCESS`), passe à l'étape suivante.
4. Ajoute une entrée dans `log.md` sous la date du jour : `* **Ingest** : raw/chemin/fichier.pdf ajouté à la BDD.`

### Maintenance de l'index
Après des ingestions massives ou si la recherche devient incohérente, reconstruis l'index FTS : `uv run skills/reindex/run.py`. Pour migrer une base ancienne vers le schéma courant (clés primaires, `keywords` en liste, colonne `embedding` + index HNSW), utilise `uv run skills/migrate-db/run.py` (dry-run par défaut, `--apply` pour exécuter).

### Embeddings (recherche vectorielle)
Chaque document porte un **embedding** (`bge-m3`, 1024-dim, stocké dans `document_content.embedding`) alimentant la recherche vectorielle. À l'ingestion, l'embedding est calculé automatiquement. Pour (re)remplir en masse (ou après une migration de schéma), lance : `uv run skills/embed-docs/run.py` (reprise sécurisée ; `--rebuild` pour tout recalculer ; `--filter "..."` pour cibler un sous-ensemble).

## 4. Flux de Requête (Question / Réponse)
Avant de répondre à **n'importe quelle** question posée par l'utilisateur concernant les documents :
1. Tu as l'interdiction de lire les fichiers `raw/` manuellement.
2. Tu DOIS utiliser ton moteur de recherche : `uv run skills/search-db/run.py "mots clés de la question"`.
3. La recherche est **hybride** par défaut : elle combine Full-Text Search (BM25) et recherche vectorielle (cosine) via une fusion Reciprocal Rank Fusion, puis renvoie les meilleurs extraits (`raw_text`) et résumés. Tu peux isoler un moteur avec `--mode fts|vector|hybrid`.
4. Formule ta réponse à l'utilisateur en te basant **exclusivement** sur ces extraits remontés par la BDD.

## 5. Maintenabilité
Si tu rencontres une erreur avec un script d'un `skill` (ex: format de fichier non supporté), tu as l'autorisation de modifier le code Python du skill pour l'améliorer (ex: ajouter le support `.xlsx` dans `ingest-doc`).
