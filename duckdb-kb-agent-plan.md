# 🚀 Projet : DuckDB KB Agent (Base Documentaire Agentique)

Ce projet est un système de gestion de connaissances nouvelle génération. Il est conçu pour être géré **intégralement par un Agent IA de codage** (comme Antigravity ou Cline). 

L'Agent n'écrit plus de fichiers Markdown statiques. Il lit les documents bruts, extrait le texte, génère une analyse sémantique (via LLM) et stocke tout le contenu (texte brut + métadonnées) dans une **base de données DuckDB**. Il utilise ensuite l'extension Full-Text Search (FTS) pour répondre instantanément aux questions de l'utilisateur.

---

## 🏗️ 1. Architecture du Projet

L'arborescence est stricte et sépare la donnée brute, la base de connaissances et les outils (skills) de l'Agent.

```text
/duckdb-kb-agent/
├── AGENTS.md               # Directives absolues pour l'Agent IA
├── pyproject.toml          # Gestion des dépendances (géré via uv)
├── knowledge.duckdb        # La base de données DuckDB (générée automatiquement)
├── log.md                  # Journal d'activité (Append-only)
├── raw/                    # [Dossier Immuable] Documents bruts (PDF, Word, Excel...)
└── skills/                 # Outils fournis à l'Agent
    ├── init-db/            # Création de la BDD et des tables SQL
    ├── ingest-doc/         # Extraction universelle et insertion BDD
    └── search-db/          # Moteur de requête (FTS + SQL) pour l'Agent
```

---

## 🐍 2. Environnement & Dépendances (Python 3.14 + `uv`)

Le projet utilise **`uv`**, le gestionnaire de paquets ultra-rapide de l'écosystème Python, avec **Python 3.14**.

### Initialisation (à faire par l'Agent lors du setup) :
```bash
# Initialiser le projet avec uv
uv init --python 3.14

# Ajouter les dépendances (dernières versions)
uv add duckdb           # Moteur de base de données analytique local
uv add pydantic         # Validation de données et Structured Output pour le LLM
uv add pymupdf          # Parsing très performant des PDF (fitz)
uv add python-docx      # Parsing des fichiers Word (.docx)
uv add pandas           # Traitement des tableaux Excel/CSV -> Markdown
uv add openai           # Client universel (compatible Ollama local ou API distantes)
uv add rich             # (Optionnel) Pour un affichage console propre des résultats
```

---

## 📜 3. Le cerveau : `AGENTS.md`

Ce fichier **doit** être créé à la racine du projet. C'est le prompt système de ton Agent.

> **Contenu exact à placer dans `AGENTS.md` :**
> 
> # Directives pour l'Agent d'Intelligence Artificielle
> 
> Tu es l'architecte et l'administrateur exclusif de la base documentaire `knowledge.duckdb`.
> 
> ## 1. Règle d'Or Absolue
> Tu ne modifies **JAMAIS** les fichiers situés dans le dossier `raw/`. C'est la source de vérité immuable. Tu ne fais qu'y lire des informations.
> 
> ## 2. Environnement Python
> Ce projet utilise `uv` et Python 3.14. Pour exécuter un script (skill), tu dois toujours utiliser `uv run` (exemple : `uv run skills/search-db/run.py`).
> 
> ## 3. Flux d'Ingestion
> Lorsque l'utilisateur te demande d'ingérer ou d'ajouter une source depuis `raw/` :
> 1. N'essaie pas de lire le fichier brut avec tes propres outils de base.
> 2. Utilise le skill dédié : exécute `uv run skills/ingest-doc/run.py "raw/chemin/fichier.pdf" --category "Tech"`.
> 3. Vérifie la sortie console du script. S'il te confirme l'insertion (Hash et succès), passe à l'étape suivante.
> 4. Ajoute une entrée dans `log.md` sous la date du jour : `* **Ingest** : raw/chemin/fichier.pdf ajouté à la BDD.`
> 
> ## 4. Flux de Requête (Question / Réponse)
> Avant de répondre à **n'importe quelle** question posée par l'utilisateur concernant les documents :
> 1. Tu as l'interdiction de lire les fichiers `raw/` manuellement.
> 2. Tu DOIS utiliser ton moteur de recherche : `uv run skills/search-db/run.py "mots clés de la question"`.
> 3. Le script te renverra dans le terminal les meilleurs extraits de texte brut (`raw_text`) et les résumés pertinents issus de DuckDB.
> 4. Formule ta réponse à l'utilisateur en te basant **exclusivement** sur ces extraits remontés par la BDD.
> 
> ## 5. Maintenabilité
> Si tu rencontres une erreur avec un script d'un `skill` (ex: format de fichier non supporté), tu as l'autorisation de modifier le code Python du skill pour l'améliorer (ex: ajouter le support `.xlsx` dans `ingest-doc`).

---

## 🗄️ 4. Les Skills (Scripts Python)

L'Agent va s'appuyer sur 3 scripts Python (qu'il pourra lui-même générer lors du démarrage du projet).

### Skill 1 : `skills/init-db/run.py`
**Rôle** : Créer le fichier `knowledge.duckdb` et initialiser les 3 tables + l'index de recherche.
- **Table `documents`** : `id` (hash SHA-256), `file_name`, `file_path`, `category`, `indexed_at`.
- **Table `document_content`** : `document_id`, `raw_text`.
- **Table `document_ai_metadata`** : `document_id`, `summary`, `keywords`.
- **Action SQL clé** : 
  ```sql
  INSTALL fts; LOAD fts;
  PRAGMA create_fts_index('document_content', 'document_id', 'raw_text');
  ```

### Skill 2 : `skills/ingest-doc/run.py`
**Rôle** : Extraire le texte d'un fichier et l'insérer en base avec l'aide de l'IA.
- **Workflow du script** :
  1. Lit l'argument CLI (chemin du fichier).
  2. Parse le fichier en fonction de son extension (`PyMuPDF` pour PDF, `python-docx` pour Word...).
  3. Formate un appel à l'API LLM (via le SDK `openai` pointant vers un Ollama local ou une API distante) en demandant un "Structured Output" (objet Pydantic `DocAnalysis(summary, keywords)`). *Si le texte dépasse 5000 mots, le script ne transmet que la Tête et la Queue au LLM*.
  4. Génère un Hash SHA-256 du fichier pour servir d'ID unique.
  5. Effectue l'insertion dans les 3 tables de DuckDB de manière sécurisée.
  6. Affiche "SUCCESS" dans le terminal pour que l'Agent comprenne que c'est terminé.

### Skill 3 : `skills/search-db/run.py`
**Rôle** : Fournir une interface de recherche fulgurante à l'Agent.
- **Workflow du script** :
  1. Prend en argument une chaîne de recherche (ex: `--query "certificat SSL"`).
  2. Exécute la requête de recherche BM25 sur l'index FTS de DuckDB :
     ```sql
     SELECT d.file_name, d.file_path, m.summary, f.score, c.raw_text
     FROM fts_main_document_content.match_bm25(?) f
     JOIN documents d ON f.document_id = d.id
     JOIN document_ai_metadata m ON d.id = m.document_id
     JOIN document_content c ON d.id = c.document_id
     ORDER BY f.score DESC LIMIT 3;
     ```
  3. Imprime les résultats de manière structurée dans le terminal. L'Agent IA lit cette sortie et utilise ces informations pour générer sa réponse conversationnelle à l'utilisateur.

---

## 🛠️ 5. Lancement du projet

Pour initier ce projet, l'utilisateur devra créer un dossier vide, l'ouvrir dans son IDE avec son Agent IA de codage (Antigravity/Cline), lui fournir ce plan et lui donner l'instruction suivante : 

*"Initialise le projet selon ce plan : crée le `pyproject.toml` avec `uv`, crée l'arborescence, génère le fichier `AGENTS.md`, et code les trois scripts Python dans les dossiers `skills/`. Exécute ensuite `init-db` pour créer la base DuckDB."*
