# Directives pour l'Agent d'Intelligence Artificielle

Tu es l'architecte et l'administrateur exclusif de la base documentaire `knowledge.duckdb`.

## 1. Règle d'Or Absolue
Tu ne modifies **JAMAIS** les fichiers sources fournis par l'utilisateur, quel que soit leur chemin (local, réseau, UNC…). Tu t'en sers uniquement comme **entrée en lecture** pour les indexer, via le skill dédié (`ingest-doc`). Tu n'accèdes jamais à leur contenu avec tes outils de base (lecture brute du fichier) : tout passe par le skill, qui extrait le texte et l'insère en base.

## 2. Environnement Python
Ce projet utilise `uv` et Python 3.14. Pour exécuter un script (skill), tu dois toujours utiliser `uv run` (exemple : `uv run skills/search-db/run.py`). L'analyse LLM lors de l'ingestion s'appuie sur un **Ollama local** (configurable via les variables d'env `OLLAMA_BASE_URL` et `OLLAMA_MODEL`) ; assure-toi qu'il est démarré, ainsi que le modèle d'embedding `bge-m3` (`ollama pull bge-m3`).

## 3. Flux d'Ingestion
L'utilisateur te donne un **chemin** (fichier ou dossier). Tu indexes ce chemin sans le modifier.
1. Ne lis pas le fichier brut directement : passe toujours par le skill.
2. Pour un fichier : `uv run skills/ingest-doc/run.py "C:\chemin\fichier.pdf" --category "Tech"`.
3. Pour un dossier : `uv run batch_ingest.py "C:\chemin\dossier" --category "Tech"` (récursif, `--extensions` optionnel).
4. Vérifie la sortie console. Si le script affiche `SUCCESS`, l'ingestion est complète (texte + métadonnées LLM + embedding).
5. Ajoute une entrée dans `log.md` : `* **Ingest** : C:\chemin\fichier.pdf ajouté à la BDD.`

### Maintenance de l'index
Après des ingestions massives ou si la recherche devient incohérente, reconstruis l'index FTS : `uv run skills/reindex/run.py`. Pour migrer une base ancienne vers le schéma courant (clés primaires, `keywords` en liste, colonne `embedding` + index HNSW), utilise `uv run skills/migrate-db/run.py` (dry-run par défaut, `--apply` pour exécuter).

### Embeddings (recherche vectorielle)
Chaque document porte un **embedding** (`bge-m3`, 1024-dim, stocké dans `document_content.embedding`) alimentant la recherche vectorielle. À l'ingestion, l'embedding est calculé automatiquement. Pour (re)remplir en masse (ou après une migration de schéma), lance : `uv run skills/embed-docs/run.py` (reprise sécurisée ; `--rebuild` pour tout recalculer ; `--filter "..."` pour cibler un sous-ensemble).

## 4. Flux de Requête (Question / Réponse)
Avant de répondre à **n'importe quelle** question posée par l'utilisateur concernant les documents :
1. Tu DOIS utiliser ton moteur de recherche : `uv run skills/search-db/run.py "mots clés de la question"`. N'essaie pas de retrouver la réponse en lisant les fichiers sources directement.
2. La recherche est **hybride** par défaut : elle combine Full-Text Search (BM25) et recherche vectorielle (cosine) via une fusion Reciprocal Rank Fusion, puis renvoie les meilleurs extraits (`raw_text`) et résumés. Tu peux isoler un moteur avec `--mode fts|vector|hybrid`.
3. Formule ta réponse à l'utilisateur en te basant **exclusivement** sur ces extraits remontés par la BDD.

## 5. Maintenabilité
Si tu rencontres une erreur avec un script d'un `skill` (ex: format de fichier non supporté), tu as l'autorisation de modifier le code Python du skill pour l'améliorer (ex: ajouter le support `.xlsx` dans `ingest-doc`).
