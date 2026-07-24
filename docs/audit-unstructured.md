# Audit technique — `Unstructured-IO/unstructured`

> Audit réalisé sur la branche `main` (juillet 2026) pour évaluer l'intégration d'Unstructured dans un pipeline d'ingestion **100 % local** (PDF / Word / HTML → texte structuré + tableaux), dans le cadre de la base de connaissances `duckdb-kb-agent`.

---

## TL;DR — Recommandation exécutive

| Critère | Verdict |
|---|---|
| **Fonctionne-t-il 100 % en local ?** | ✅ Oui, via `partition_pdf()` / `partition()` — aucun appel réseau par défaut |
| **Embarque-t-il du cloud ?** | ⚠️ `unstructured-client` (SDK SaaS) est une dépendance **de base** (inutile mais installée) |
| **La qualité layout/tables vaut-elle le coût ?** | ✅ Oui **uniquement** en stratégie `hi_res` |
| **`hi_res` s'installe-t-il sur Windows natif ?** | ❌ Non — `torch`/`unstructured-inference` sont explicitement exclus de Windows dans `pyproject.toml` |
| **Recommandation finale** | **Contourné sur Windows natif** ; envisager Unstructured **dans un conteneur Docker/WSL2** OU un stack léger alternatif (`pdfplumber` + `mammoth` + `trafilatura`) |

Voir [§5 — Évaluation critique](#5-évaluation-critique--poids-complexité) et [§7 — Recommandations](#7-recommandations-dintégration).

---

## 1. Architecture globale

### 1.1 Structure racine du dépôt

```
unstructured/              # package Python principal
test_unstructured/         # tests unitaires
test_unstructured_ingest/  # tests d'intégration (connecteurs)
example-docs/              # documents d'exemple (PDF, DOCX, EML...)
docker/                    # Dockerfiles
scripts/                   # scripts utilitaires
pyproject.toml             # ⭐ config unique (plus de setup.py)
Makefile, Dockerfile, environment.yml, uv.lock
```

> ⚠️ **`setup.py` n'existe plus** (HTTP 404). Le projet a migré vers **Hatchling** avec `pyproject.toml` comme seule source de configuration. C'est ce fichier qui définit les `extras_require` (section `[project.optional-dependencies]`).

### 1.2 Sous-modules du package `unstructured/`

| Dossier | Rôle | Pertinence pour nous |
|---|---|---|
| `unstructured/partition/` | **Cœur** : un partitionneur par type de fichier (30+ backends) | ⭐ INDISPENSABLE |
| `unstructured/partition/pdf_image/` | Logique PDF/image : OCR, pdfminer, formulaires | ⭐ INDISPENSABLE |
| `unstructured/chunking/` | Stratégies de découpage (`basic`, `title`, `dispatch`) | ⭐ Utile |
| `unstructured/cleaners/` | Nettoyage texte (regex, bullets, encodage) | ⭐ Utile |
| `unstructured/documents/` | Modèle `Element`, `Page`, métadonnées | ⭐ INDISPENSABLE |
| `unstructured/staging/` | Export (dict, JSON, DataFrame, HuggingFace, Weaviate...) | ⚠️ Partiellement utile |
| `unstructured/file_utils/` | Détection de type (`detect_filetype`, énum `FileType`) | ⭐ INDISPENSABLE |
| `unstructured/nlp/` | Tokenizer spaCy, patterns regex | Utile (tokenizer) |
| `unstructured/embed/` | Embeddings (OpenAI...) | ❌ Inutile |
| `unstructured/metrics/` | Métriques internes | ❌ Inutile |
| `unstructured/patches/` | Patches de compat tiers | ❌ Inutile |
| `unstructured/safe_http.py` | HTTP pour l'API SaaS | ❌ Inutile (cloud) |
| `unstructured/partition/api.py` | `partition_via_api()` (API REST Unstructured) | ❌ Inutile (cloud) |

> ℹ️ **Important** : `unstructured/ingest/` (les connecteurs cloud S3/Azure/GCS/Salesforce...) **n'est plus dans ce dépôt**. Il a été extrait vers un package séparé `unstructured-ingest`, installable via l'extra `[ingest]`. Ne pas installer cet extra ⇒ zéro connecteur cloud.

### 1.3 Fichiers clés du module `partition/`

```
unstructured/partition/
├── auto.py                 # ⭐ partition() — routeur auto + détection de type
├── pdf.py                  # ⭐ partition_pdf() (1534 lignes, le plus complexe)
├── strategies.py           # dispatch fast/hi_res/ocr_only/auto
├── model_init.py           # init/téléchargement des modèles de layout
├── api.py                  # partition_via_api() (cloud — à éviter)
├── docx.py  doc.py  pptx.py  ppt.py  xlsx.py  csv.py  html/  ...
├── pdf_image/
│   ├── ocr.py  pdfminer_processing.py  pdfminer_utils.py
│   ├── pypdf_utils.py  form_extraction.py  inference_utils.py
└── utils/
    ├── constants.py        # PartitionStrategy, OCRMode, OCR_AGENT_*
    ├── config.py  sorting.py  xycut.py
    └── ocr_models/         # tesseract_ocr.py, paddle_ocr.py, google_vision_ocr.py
```

---

## 2. Modules d'extraction (Partitioning)

### 2.1 `partition()` — le routeur automatique

**Fichier** : `unstructured/partition/auto.py` (372 lignes)

Fonctionnement :
1. **Détection du type** via `detect_filetype()` (importé de `unstructured.file_utils.filetype`) — utilise **libmagic** (MIME), complété par le contenu et l'extension en fallback.
2. **Routage** vers le bon partitionneur via la classe `_PartitionerLoader` qui charge **dynamiquement** le module via `importlib` :

```python
# auto.py, _PartitionerLoader._load_partitioner
partitioner_module = importlib.import_module(file_type.partitioner_module_qname)
return getattr(partitioner_module, file_type.partitioner_function_name)
```

Le routage est **piloté par les données** (l'énum `FileType` dans `file_utils/model.py` contient `partitioner_module_qname`, `partitioner_function_name`, `importable_package_dependencies`, `extra_name` pour chaque type). Pas de grand `if/elif` procédural.

3. **Post-traitement** `augment_metadata()` ajoute `url`, `data_source`, `filetype` aux métadonnées de chaque élément.

### 2.2 Liste exhaustive des fonctions `partition_*` (28 types)

| Type de fichier | Fonction | Module | Extra pip |
|---|---|---|---|
| BMP/HEIC/JPG/PNG/TIFF | `partition_image` | `partition/image.py` | `[image]` |
| **PDF** | **`partition_pdf`** | **`partition/pdf.py`** | `[pdf]` (= `[image]`) |
| **DOCX** | **`partition_docx`** | `partition/docx.py` | `[docx]` |
| DOC | `partition_doc` | `partition/doc.py` | `[doc]` (→ conversion) |
| **PPTX** | `partition_pptx` | `partition/pptx.py` | `[pptx]` |
| PPT | `partition_ppt` | `partition/ppt.py` | `[ppt]` (→ conversion) |
| **XLSX/XLS** | `partition_xlsx` | `partition/xlsx.py` | `[xlsx]` |
| CSV/TSV | `partition_csv` / `partition_tsv` | `partition/csv.py` | `[csv]`/`[tsv]` |
| **HTML** | `partition_html` | `partition/html/partition.py` | (base) |
| MD | `partition_md` | `partition/md.py` | `[md]` |
| EML/MSG | `partition_email` / `partition_msg` | `partition/email.py` | (base) / `[msg]` |
| EPUB/ODT/RTF/RST/ORG | `partition_*` | `partition/*.py` | via `[pypandoc]` |
| TXT/JSON/NDJSON/XML | `partition_*` | `partition/*.py` | (base) |
| Audio | `partition_audio` | `partition/audio.py` | `[audio]` |

### 2.3 `partition_pdf()` en détail

**Fichier** : `unstructured/partition/pdf.py` (1534 lignes)

#### Bibliothèques utilisées
- **`pdfminer.six`** — extraction du texte natif
- **`pypdf`** — lecture de la structure PDF
- **`Pillow` (PIL)** + `pi_heif` — rendu images
- **`unstructured_inference`** (package séparé) — modèles de layout/OCR/tables

#### Les 4 stratégies (`PartitionStrategy`, `partition/utils/constants.py`)
| Stratégie | Description | Layout/Tables | OCR | Lourdeur |
|---|---|---|---|---|
| `fast` | Extraction texte directe (pdfminer) | ❌ | ❌ | 🟢 légère |
| `ocr_only` | OCR Tesseract sur tout | ❌ | ✅ | 🟡 moyenne |
| `hi_res` | **Modèle de layout + tables** | ✅ | ✅ (si besoin) | 🔴 lourde (modèle ML) |
| `auto` (défaut) | `hi_res` si tables/images, sinon `fast` si texte extractible, sinon `ocr_only` | dépend | dépend | — |

**⚠️ Gotcha critique** : `infer_table_structure=True` (→ `metadata.text_as_html`) n'est effectif **qu'en `hi_res`**. En `fast`/`ocr_only`, pas de structure de table.

#### Pipeline interne de `hi_res` (`_partition_pdf_or_image_local()`)
1. **Layout inference** via `unstructured_inference.inference.layout` → modèle **YOLOX** (défaut) ou Detectron2-ONNX
2. **Extraction pdfminer** du texte natif (`process_file_with_pdfminer`)
3. **Fusion** layout OD (modèle) + layout extrait (`merge_inferred_with_extracted_layout`)
4. **OCR** sur le layout fusionné si nécessaire
5. **Construction** de la liste d'`Element`s avec tri spatial (`sort_page_elements`, algorithme XY-cut)
6. **Table Transformer** (Microsoft) si `infer_table_structure=True` → génère le HTML

#### Modèles de layout (package externe `unstructured_inference`)
- **Modèle par défaut** : `DEFAULT_MODEL = "yolox"` (`unstructured_inference/models/base.py`)
  - Checkpoint : `unstructuredio/yolo_x_layout` sur HuggingFace (plusieurs centaines de Mo)
- **Detectron2-ONNX** : alternative ("le plus rapide"), contourne la compilation Detectron2
- **Table Transformer** : `microsoft/table-transformer-structure-recognition` (~100 Mo)
- **Sélection** via env vars : `UNSTRUCTURED_HI_RES_MODEL_NAME`, `UNSTRUCTURED_HI_RES_SUPPORTED_MODEL`
- **Téléchargement** au premier run depuis HuggingFace Hub (cache `~/.cache/huggingface/`)

#### ⚠️ Fallback silencieux dangereux
Si `unstructured_inference` est mal installé, Unstructured **retombe silencieusement sur `fast`** avec un message d'avertissement. Tu crois avoir du `hi_res`, tu n'as ni layout ni tables. **Toujours vérifier la stratégie réellement utilisée dans les logs.**

### 2.4 Modules Office

| Format | Fonction | Lib sous-jacente | Particularité |
|---|---|---|---|
| `.docx` | `partition_docx()` | `python-docx` | Architecture itérative (`_DocxPartitioner`), gère tables, headers/footers, hyperliens |
| `.doc` | `partition_doc()` | → **LibreOffice** | Convertit `.doc` → `.docx` puis délègue à `partition_docx()` |
| `.pptx` | `partition_pptx()` | `python-pptx` | Parcourt slides/shapes, gère tables, notes |
| `.ppt` | `partition_ppt()` | → **LibreOffice** | Convertit `.ppt` → `.pptx` |
| `.xlsx` | `partition_xlsx()` | `pandas` + `openpyxl` + `networkx` | Détecte les sous-tables (composantes connexes), `msoffcrypto` pour fichiers chiffrés |

> ⚠️ Les formats legacy (`.doc`, `.ppt`, `.xls`, `.odt`) nécessitent **LibreOffice en headless** au niveau système.

### 2.5 HTML

**Fichier** : `unstructured/partition/html/partition.py` (293 lignes)

Utilise **`lxml`** + **`beautifulsoup4`**. Deux versions de parser :
- `html_parser_version="v1"` — parser flow-based
- `html_parser_version="v2"` — ontologie/schema via `parse_html_to_ontology`

Supporte `skip_headers_and_footers`, extraction d'images. **Aucun extra requis** (géré par les dépendances de base).

---

## 3. Gestion des dépendances locales

### 3.1 Dépendances Python de BASE (toujours installées)

Extrait de `pyproject.toml` `[project] dependencies` :

```
beautifulsoup4, charset-normalizer, emoji, filetype, html5lib,
langdetect, lxml, nh3, spacy, installer, numba, numpy, psutil,
python-iso639, python-magic, python-oxmsg, rapidfuzz, regex,
requests, tqdm, typing-extensions,
unstructured-client,        # ⚠️ SDK SaaS (inutile mais imposé)
wrapt, filelock
```

> ⚠️ **`unstructured-client` est une dépendance de base** — le SDK qui parle à `api.unstructured.io`. Il est installé même si tu n'appelles jamais `partition_via_api()`. Pour un environnement air-gap strict, il faudra le désinstaller ou bloquer le domaine au firewall.

### 3.2 Extras pour 100 % local (PDF + OCR + Office + HTML)

**Extra agrégat** : `local-inference = ["unstructured[all-docs]"]`

#### `pdf` (= alias vers `image`) — cœur PDF + OCR
```
pdf2image>=1.17.0             # dépend de poppler
pdfminer.six>=20251230
pi-heif>=1.2.0                # HEIF/HEIC
pikepdf>=10.3.0
pypdf>=6.6.2
unstructured-inference>=1.6.12    # ⚠️ layout/tables (YOLOX/Detectron2/Table-Transformer)
unstructured-pytesseract>=0.3.15  # OCR Tesseract
# google-cloud-vision (optionnel cloud)
```

> ⚠️ **`unstructured-inference` est restreint hors Windows** (ou Windows + Python 3.12 uniquement) dans les marqueurs de plateforme.

#### Office
```
docx = ["python-docx>=1.2.0"]
doc  = ["unstructured[docx]"]          # .doc → docx via LibreOffice
pptx = ["python-pptx>=1.0.2"]
ppt  = ["unstructured[pptx]"]          # .ppt → pptx via LibreOffice
xlsx = ["msoffcrypto-tool", "networkx", "openpyxl", "pandas", "xlrd"]
csv  = ["pandas"]
```

#### Layout / OCR alternatifs
```
huggingface = ["sentencepiece", "torch>=2.10.0", "transformers>=5.2.0"]
             # ⚠️ torch explicitement EXCLU de Windows (platform_system != 'Windows')
paddleocr   = ["paddlepaddle>=3.3.0", "unstructured-paddleocr==2.10.0"]
```

#### HTML
**Aucun extra** — géré par les dépendances de base (`beautifulsoup4`, `lxml`, `html5lib`, `nh3`).

### 3.3 Dépendances SYSTÈME (non-Python, obligatoires)

| Outil | Rôle | Ubuntu/Debian |
|---|---|---|
| **libmagic** | Détection de filetype | `libmagic-dev` / `libmagic1` |
| **poppler** | Rasterisation PDF → image (`pdf2image`) | `poppler-utils` |
| **tesseract-ocr** | OCR | `tesseract-ocr` (+ `tesseract-ocr-fra`, `tesseract-ocr-eng`) |
| **libreoffice** | Conversion docs MS Office legacy | `libreoffice` |
| **pandoc** | Formats EPUB/ODT/RTF/RST/ORG | (fourni par `pypandoc-binary`, binaire embarqué) |

**Commande Ubuntu** :
```bash
apt-get install -y libmagic1 poppler-utils tesseract-ocr \
                   tesseract-ocr-fra tesseract-ocr-eng libreoffice
```

**Sur Windows** : ces binaires existent (via conda, chocolatey, ou téléchargement manuel) mais doivent être configurés manuellement (variables `PATH`, `TESSDATA_PREFIX`, etc.).

### 3.4 Modèles de layout (à pré-télécharger pour l'offline)

| Modèle | Origine | Taille approx. | Usage |
|---|---|---|---|
| **YOLOX layout** | `unstructuredio/yolo_x_layout` (HuggingFace) | ~centaines de Mo | Détection layout (défaut) |
| **Table Transformer** | `microsoft/table-transformer-structure-recognition` | ~100 Mo | Structure des tables |
| **Detectron2-ONNX** | `unstructured/unstructured-transformer-models` | variable | Layout alternatif |
| **spaCy** | `en_core_web_sm` | ~12 Mo | Tokenizer de phrases |
| **Tesseract traineddata** | `tesseract-ocr/tessdata` | centaines de Mo | Données OCR |

**Pré-téléchargement** :
```python
from unstructured.partition.model_init import initialize
initialize()   # télécharge YOLOX + modèles supportés
# + pré-charger le Table Transformer via unstructured_inference
```

**Mode offline** : poser `HF_HUB_OFFLINE=1` après pré-téléchargement.

### 3.5 Variables d'environnement utiles

```bash
UNSTRUCTURED_HI_RES_MODEL_NAME=yolox     # modèle de layout
UNSTRUCTURED_HI_RES_SUPPORTED_MODEL=     # modèles additionnels (CSV)
HF_HUB_OFFLINE=1                         # mode offline (après pré-téléchargement)
TESSDATA_PREFIX=/usr/local/share/tessdata
UNSTRUCTURED_TELEMETRY_ENABLED=0         # désactive la télémétrie
DO_NOT_TRACK=1                           # opt-out télémétrie
SCARF_NO_ANALYTICS=1
```

---

## 4. Exemples et bonnes pratiques

### 4.1 Syntaxe minimale — extraction PDF locale complète

```python
from unstructured.partition.pdf import partition_pdf

elements = partition_pdf(
    filename="doc.pdf",
    strategy="hi_res",          # "fast" | "ocr_only" | "hi_res" | "auto"(défaut)
    infer_table_structure=True, # ⚠️ effectif uniquement en hi_res
    languages=["eng", "fra"],   # langues OCR Tesseract (remplace ocr_languages déprécié)
    # hi_res_model_name="yolox",  # modèle de layout (None = défaut yolox)
    # include_page_breaks=False,
    # starting_page_number=1,
)

for el in elements:
    print(el.category)                    # "Title" | "Table" | "NarrativeText" | ...
    print(el.text)                        # texte ou contenu de la table
    print(el.metadata.page_number)        # numéro de page
    print(el.metadata.text_as_html)       # HTML <table> (uniquement pour Table en hi_res)
```

### 4.2 Accès aux métadonnées

| Attribut | Description |
|---|---|
| `element.text` | Texte / contenu (pas de `text_content`) |
| `element.category` | Type (`"Title"`, `"Table"`, `"NarrativeText"`...) |
| `element.metadata.page_number` | Numéro de page |
| `element.metadata.text_as_html` | HTML de la table (uniquement si `infer_table_structure=True` + `hi_res`) |

Classe : `ElementMetadata` (`unstructured/documents/elements.py`), objet dynamique.

### 4.3 Récupération des TABLEAUX

```python
tables = [el for el in elements if el.category == "Table"]

for t in tables:
    html = t.metadata.text_as_html   # <table>...</table> (hi_res + infer_table_structure)
    text = t.text                    # version texte de la table
    page = t.metadata.page_number
```

### 4.4 Paramètres importants

| Paramètre | Défaut | Usage |
|---|---|---|
| `strategy` | `"auto"` | `"fast"` = texte direct ; `"hi_res"` = layout+tables ; `"ocr_only"` = OCR partout |
| `infer_table_structure` | `False` | Uniquement en `hi_res` → produit `text_as_html` |
| `languages` | `None` | Liste de codes Tesseract (`["eng","fra"]`) |
| `ocr_languages` | `None` | ⚠️ **Déprécié** → utiliser `languages` |
| `hi_res_model_name` | `None` (= yolox) | Modèle de layout |
| `model_name` | — | ⚠️ **Déprécié** → `hi_res_model_name` |
| `include_page_breaks` | `False` | Insère des `PageBreak` |
| `extract_images_in_pdf` | `False` | Extrait images embarquées |
| `password` | `None` | PDF chiffré |

### 4.5 Types d'éléments (`ElementType`, `unstructured/documents/elements.py`)

| Classe | `category` | Usage |
|---|---|---|
| `Title` | `"Title"` (aussi Section-header, Headline...) | Titres |
| `NarrativeText` | `"NarrativeText"` (aussi Text, Paragraph) | Texte courant |
| `ListItem` | `"ListItem"` | Éléments de liste |
| `Table` | `"Table"` | Tableaux |
| `TableChunk` | `"TableChunk"` | Fragment de table après chunking |
| `Header` / `Footer` | `"Header"` / `"Footer"` | En-têtes/pieds |
| `Image` | `"Image"` (Picture, Figure) | Images |
| `FigureCaption` | `"FigureCaption"` | Légendes |
| `PageBreak` | `"PageBreak"` | Sauts de page |
| `Formula`, `Address`, `EmailAddress`, `CodeSnippet`, `PageNumber`, `Form` | homonymes | Spécialisés |
| `CompositeElement` | `"CompositeElement"` | Produit par le chunking |

### 4.6 Chunking

#### `chunk_by_title` (`unstructured/chunking/title.py`)
Découpe en sections délimitées par les `Title`.

```python
from unstructured.chunking.title import chunk_by_title

chunks = chunk_by_title(
    elements,
    max_characters=1500,
    new_after_n_chars=1200,
    combine_text_under_n_chars=300,
    multipage_sections=True,
    include_orig_elements=True,
    repeat_table_headers=True,
    isolate_table=True,         # chaque table dans son propre chunk
)
```

#### `chunk_elements` (`unstructured/chunking/basic.py`)
Chunking séquentiel avec overlap.

```python
from unstructured.chunking.basic import chunk_elements
chunks = chunk_elements(elements, max_characters=1500, overlap=100)
```

**Raccourci** : `partition_pdf(..., chunking_strategy="by_title")` applique le chunking directement.

---

## 5. Évaluation critique — poids & complexité

### 5.1 Poids

- **Taille dépôt** : ~237 Mo (code source seul, hors modèles ML)
- **Dépendances de base** : déjà 24 paquets Python (dont `spacy`, `numba`, `unstructured-client`)
- **Modèles au runtime** : + centaines de Mo (YOLOX layout + Table Transformer + spaCy)
- **Stack complet `hi_res`** : probablement **500 Mo - 1 Go** une fois modèles + torch + opencv installés

### 5.2 Autonomie 100 % locale

| Question | Réponse |
|---|---|
| `partition_pdf()` fait-il des appels réseau ? | ❌ Non par défaut |
| La télémétrie est-elle active ? | ❌ Non par défaut (`UNSTRUCTURED_TELEMETRY_ENABLED` à opt-in) |
| `unstructured-client` (cloud) est-il installé ? | ⚠️ Oui, mais jamais appelé spontanément |
| Premier run `hi_res` nécessite-t-il internet ? | ✅ Oui (téléchargement modèles HuggingFace) |

**Conclusion** : 100 % local est **réellement possible** après pré-téléchargement des modèles. Pour l'air-gap strict, supprimer `unstructured-client` et bloquer `api.unstructured.io`.

### 5.3 Complexité d'installation — ⚠️ le mur Windows

| Composant | Linux | macOS | Windows natif |
|---|---|---|---|
| Base Unstructured | ✅ | ✅ | ✅ |
| `fast` / `ocr_only` | ✅ | ✅ | ✅ |
| **`hi_res` (YOLOX/inference)** | ✅ | ✅ | ❌ **`torch` exclu de Windows** dans `pyproject.toml` |
| Detectron2 (historique) | ✅ | ✅ | ❌ Non supporté officiellement |
| LibreOffice (doc/ppt legacy) | ✅ | ✅ | ⚠️ Manuelle |

**Signal officiel** : `torch>=2.10.0` dans l'extra `huggingface` est marqué `platform_system != 'Windows'`. Le projet est clairement **orienté Linux/Docker**. Solutions officielles pour Windows : **WSL2 ou Docker**.

**Le piège** : si `unstructured-inference` ne s'installe pas, Unstructured **fallback silencieusement sur `fast`** sans erreur — tu perds layout ET tables sans le savoir.

### 5.4 Modules à ÉVITER d'installer

| Extra / Module | Pourquoi l'éviter |
|---|---|
| `[ingest]` | Connecteurs cloud (S3/Azure/GCS/Salesforce...) — inutile en local |
| `[huggingface]` | Tire `torch` (exclu Windows) — déjà couvert par `unstructured-inference` |
| `[audio]` | Whisper pour l'audio |
| `[paddleocr]` | Alternative OCR lourde (PaddlePaddle) |
| `[chunking-tokens]` | Comptage tokens LLM (tiktoken) |
| `unstructured/embed/`, `metrics/`, `patches/`, `safe_http.py`, `partition/api.py` | Inutiles pour extraction pure |

---

## 6. Alternatives légères 100 % locales

Comparatif pour un stack **sans Unstructured** (licences permissives, native Windows) :

| Besoin | Bibliothèque | Licence | Layout/Tables | Poids | Note |
|---|---|---|---|---|---|
| **PDF texte + tables** | **pdfplumber** | MIT | ✅ Tables excellentes (`extract_tables`) | Très faible | ⭐ Meilleur compromis léger |
| PDF texte rapide | pypdfium2 | BSD-3/Apache | ❌ Texte seulement | Très faible | Champion vitesse |
| PDF tout-en-un | PyMuPDF | ⚠️ **AGPL-3** | ✅ | Faible | ⚠️ Licence AGPL = incompatible propriétaire fermé |
| PDF tables (lattice/stream) | camelot-py | MIT | ✅ | Faible | Dépend ghostscript + tkinter |
| PDF → Markdown | marker-pdf | ⚠️ **GPL-3** | ✅ | Moyenne | ⚠️ GPL |
| **DOCX → HTML/MD** | **mammoth** | BSD-2 | Structure/styles | Très faible | ⭐ Référence DOCX propre |
| DOCX | python-docx | MIT | Paragraphes + tables | Très faible | Contrôle bas niveau |
| **HTML contenu principal** | **trafilatura** | Apache-2 | ✅ Meta + tables | Très faible | ⭐ Meilleur pour HTML bruité |
| HTML DOM | beautifulsoup4 + lxml | MIT | Complet | Très faible | Déjà dépendance Unstructured |

### Stack alternatif recommandé (~30-40 Mo total)
```
PDF    : pdfplumber (tables) + pypdfium2 (fallback rapide) + pytesseract (OCR si scanné)
DOCX   : mammoth (conversion propre) OU python-docx (contrôle fin)
HTML   : trafilatura (contenu principal) + beautifulsoup4/lxml (DOM)
Chunk. : chunker maison (~50 lignes) — la logique titre/overlap est triviale
```

**À éviter** : PyMuPDF (AGPL) et Marker (GPL) si contraintes de licence propriétaire.

---

## 7. Recommandations d'intégration

### 7.1 Trois scénarios possibles

#### Scénario A — Unstructured dans Docker/WSL2 (qualité maximale PDF complexes)
```dockerfile
# Dockerfile basé sur l'image officielle ou Chainguard/Wolfi
# + apt: libmagic1 poppler-utils tesseract-ocr libreoffice
# + pré-téléchargement des modèles YOLOX + Table Transformer
ENV HF_HUB_OFFLINE=1
ENV UNSTRUCTURED_TELEMETRY_ENABLED=0
```
```bash
pip install "unstructured[pdf,docx,pptx,xlsx,csv]"  # PAS [ingest], PAS [huggingface]
```
- ✅ Qualité layout/tables maximale
- ❌ Lourd, conteneur obligatoire, complexité ops

#### Scénario B — Stack léger alternatif (recommandé si Windows natif)
```bash
pip install pdfplumber pypdfium2 pytesseract mammoth python-docx trafilatura beautifulsoup4 lxml
# + système : tesseract (via conda/choco sur Windows)
```
- ✅ Installation en 30 secondes, natif Windows, ~30-40 Mo
- ✅ Aucune dépendance cloud, licences MIT/Apache
- ⚠️ Qualité tables légèrement inférieure sur PDF très complexes/scannés
- ⚠️ Nécessite d'écrire un routeur type-fichier (~50 lignes) pour remplacer `partition.auto`

#### Scénario C — Hybride (le meilleur des deux)
- **Stack léger** (`pdfplumber` + `mammoth` + `trafilatura`) pour 95 % des documents (PDF born-digital, DOCX, HTML)
- **Conteneur Docker Unstructured `hi_res`** comme fallback pour les PDF scannés/complexes problématiques
- Routage : détecter si `pdfplumber` extrait peu de texte → envoyer au conteneur `hi_res`

### 7.2 Décision recommandée pour `duckdb-kb-agent`

Compte tenu du contexte (base de connaissances locale, agents autonomes, environnement Windows d'après le `gitStatus` du projet) :

> **Privilégier le Scénario B (stack léger)** comme socle d'ingestion.
> Garder l'option Docker `hi_res` (Scénario C) comme fallback conteneurisé pour les PDF difficiles.

**Justifications** :
1. `hi_res` (la seule stratégie qui justifie Unstructured) **ne s'installe pas sur Windows natif**
2. Les dépendances cloud (`unstructured-client`) et la lourdeur (torch, opencv, modèles 500 Mo+) sont disproportionnées pour un agent local
3. `pdfplumber` rivalise avec `hi_res` sur la majorité des PDF non-scannés, sans aucune de ces contraintes
4. Le routeur `partition.auto` est reproductible en ~50 lignes avec `python-magic` + dispatch

### 7.3 Si tu choisis quand même Unstructured — isolation réseau

```python
# 1. Ne jamais installer [ingest]
pip install "unstructured[pdf,docx,pptx,xlsx,csv]"  # PAS [ingest], PAS [huggingface]

# 2. Variables d'env pour isolation
import os
os.environ["UNSTRUCTURED_TELEMETRY_ENABLED"] = "0"
os.environ["DO_NOT_TRACK"] = "1"
os.environ["SCARF_NO_ANALYTICS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"  # après pré-téléchargement des modèles

# 3. Optionnel : désinstaller unstructured-client après install
# pip uninstall unstructured-client

# 4. TOUJOURS vérifier la stratégie réellement utilisée (détecter le fallback silencieux)
import logging
logging.getLogger("unstructured").setLevel(logging.INFO)
```

### 7.4 Risques résiduels (si Unstructured)

1. **Fallback silencieux `hi_res → fast`** sans erreur explicite → vérifier les logs
2. **`unstructured-client` en dépendance de base** → supprimer pour air-gap
3. **Téléchargement runtime du modèle YOLOX** au premier appel → pré-télécharger
4. **`torch` exclu de Windows** par construction → conteneur obligatoire
5. **Versions très récentes requises** (`torch>=2.10`, `transformers>=5.2`) → friction potentielle avec autres packages

---

## 8. Fichiers clés de référence

| Chemin | Rôle |
|---|---|
| `pyproject.toml` (racine) | Config unique + extras (remplace `setup.py`) |
| `Dockerfile` (racine) | Image Chainguard/Wolfi officielle |
| `unstructured/partition/auto.py` | Routeur `partition()` + détection type |
| `unstructured/partition/pdf.py` | `partition_pdf()` (1534 lignes) |
| `unstructured/partition/strategies.py` | Dispatch fast/hi_res/ocr_only/auto |
| `unstructured/partition/model_init.py` | Init modèles de layout |
| `unstructured/file_utils/model.py` | Énum `FileType` (routage piloté par données) |
| `unstructured/file_utils/filetype.py` | `detect_filetype()` (libmagic) |
| `unstructured/documents/elements.py` | `Element`, `ElementType`, `ElementMetadata` |
| `unstructured/chunking/title.py` | `chunk_by_title()` |
| `unstructured/chunking/basic.py` | `chunk_elements()` |
| `unstructured/partition/utils/constants.py` | `PartitionStrategy`, OCR agents |
| `example-docs/` | Documents d'exemple (PDF, DOCX, EML...) |

**Dépôt externe** : `Unstructured-IO/unstructured-inference` — contient les modèles ML (YOLOX, Detectron2-ONNX, Table Transformer), `DEFAULT_MODEL = "yolox"`.

---

*Audit réalisé le 2026-07-24 sur la branche `main` du dépôt `Unstructured-IO/unstructured`.*
