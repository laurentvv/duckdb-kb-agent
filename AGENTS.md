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
4. Vérifie la sortie console. Si le script affiche `SUCCESS`, l'ingestion est complète (extraction structurée → chunks → métadonnées LLM → embedding document + embeddings chunks).
5. Ajoute une entrée dans `log.md` : `* **Ingest** : C:\chemin\fichier.pdf ajouté à la BDD.`

### Pipeline d'ingestion (détail)
Chaque document subit, dans l'ordre :
1. **Extraction structurée** (`parsing.extract_elements`) : le fichier est découpé en éléments typés (Title, NarrativeText, Table, ListItem) avec conservation du **numéro de page** (PDF) et de la **section** courante. Routeur par extension : PDF (pdfplumber, tables extraites), DOCX (python-docx, headings + tables), HTML (trafilatura), XLSX/CSV, texte/Markdown.
2. **Chunking sémantique** (`parsing.chunk_elements`) : les éléments sont regroupés en chunks cohérents (~600-1200 car.) en respectant la structure (un titre démarre une nouvelle frontière si le chunk courant est assez gros ; une table reste dans un chunk dédié). Plafond de 100 chunks par document (anti-explosion).
3. **Résumé LLM** (`analyze_text`) : summary + keywords via le modèle local.
4. **Embeddings** : un embedding `bge-m3` (1024-dim) par document ET un embedding par chunk.
5. **Insertion transactionnelle** dans `documents`, `document_content`, `document_ai_metadata`, `chunks`.

### Dédoublonnage intelligent
- Document **non modifié** (même contenu = même hash SHA-256) → **skippé** (pas de recalcul).
- Document **modifié** (même `file_path`, contenu différent) → **mise à jour** : l'ancienne version et ses chunks sont purgés, la nouvelle est insérée.
- `--force` force la ré-ingestion même si le contenu est identique.

### Maintenance de l'index
Après des ingestions massives ou si la recherche devient incohérente, reconstruis l'index FTS : `uv run skills/reindex/run.py`. Pour migrer une base ancienne vers le schéma courant (clés primaires, `keywords` en liste, colonne `embedding` + index HNSW, **table `chunks`** + index FTS/HNSW), utilise `uv run skills/migrate-db/run.py` (dry-run par défaut, `--apply` pour exécuter).

### Embeddings (recherche vectorielle)
Chaque document porte un **embedding** (`bge-m3`, 1024-dim, dans `document_content.embedding`) ET chaque chunk porte son propre embedding (dans `chunks.embedding`), alimentant la recherche vectorielle aux deux niveaux. À l'ingestion, les embeddings sont calculés automatiquement. Pour (re)remplir en masse, lance : `uv run skills/embed-docs/run.py` (reprise sécurisée ; `--rebuild` pour tout recalculer ; `--chunks-only` pour les chunks uniquement ; `--filter "..."` pour cibler un sous-ensemble).

## 4. Flux de Requête (Question / Réponse)
Avant de répondre à **n'importe quelle** question posée par l'utilisateur concernant les documents :
1. Tu DOIS utiliser ton moteur de recherche : `uv run skills/search-db/run.py "mots clés de la question"`. N'essaie pas de retrouver la réponse en lisant les fichiers sources directement.
2. La recherche est **hybride** par défaut et opère au **niveau chunk** : elle combine Full-Text Search (BM25 sur `chunks.text`) et recherche vectorielle (cosine sur `chunks.embedding`) via une fusion Reciprocal Rank Fusion, regroupe les chunks par document (diversification des sources), puis renvoie les meilleurs extraits avec leurs **métadonnées de structure** (page, section, type d'élément). Tu peux isoler un moteur avec `--mode fts|vector|hybrid`.
3. Formule ta réponse à l'utilisateur en te basant **exclusivement** sur ces extraits remontés par la BDD. **Cite la source** (fichier, page/section) quand l'information est disponible dans les métadonnées du chunk.

## 5. Maintenabilité
Si tu rencontres une erreur avec un script d'un `skill` (ex: format de fichier non supporté), tu as l'autorisation de modifier le code Python du skill pour l'améliorer (ex: ajouter le support `.xlsx` dans `ingest-doc`).
