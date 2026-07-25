# Réindexation avec Vision LLM

> Procédure pour ré-ingérer les documents existants en activant la description des images (captures d'écran, PDF scannés, schémas) via le modèle multimodal Gemma 4.

## Quand faire cette réindexation ?

Beaucoup de documents métier (modes opératoires, procédures) contiennent des **captures d'écran** de logiciels, de sites web, ou des schémas. Ces images sont actuellement **ignorées** par l'extraction — seul le texte est indexé. La réindexation avec vision permet de rendre leur contenu **recherchable**.

**Volume estimé** : ~169 documents (DOCX + PDF) susceptibles de contenir des captures d'écran sur le corpus actuel.

## ⚠️ Points importants avant de commencer

1. **C'est LONG** : ~15-30 secondes par image détectée. Pour 169 documents, prévoir **plusieurs heures** (variable selon le nombre d'images par document).
2. **Opt-in** : la vision n'est activée que pour cette réindexation — les futures ingestions restent sans vision sauf si tu ajoutes `--vision`.
3. **Reprise** : tu peux interrompre (Ctrl+C) et relancer — les documents déjà retraités avec vision ne seront pas refaits (le hash change car le contenu indexé change).
4. **Ollama requis** : le modèle Gemma 4 E4B (`hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL`) doit être présent. Vérifier :
   ```bash
   curl http://localhost:11434/api/tags
   ```

## 🚀 Procédure de réindexation

### Option A — Script dédié (recommandé)

Le script `skills/reindex-vision/run.py` automatise tout : il parcourt les documents existants, purge l'ancienne version, et ré-ingère avec `--vision --force`. Il gère la reprise et affiche l'ETA.

```bash
cd D:\GIT\duckdb-kb-agent

# 1. Test rapide sur 3 documents (valider que la vision marche)
uv run skills/reindex-vision/run.py --limit 3

# 2. Réindexer uniquement les DOCX (captures d'écran les plus fréquentes)
uv run skills/reindex-vision/run.py --filter "file_path ILIKE '%.docx'"

# 3. Réindexer uniquement les PDF
uv run skills/reindex-vision/run.py --filter "file_path ILIKE '%.pdf'"

# 4. Réindexer TOUT
uv run skills/reindex-vision/run.py
```

**Lancer en arrière-plan** (pour ne pas bloquer le terminal) :
```powershell
# Dans PowerShell
$env:PYTHONUNBUFFERED=1
uv run skills/reindex-vision/run.py --filter "file_path ILIKE '%.docx'" 2>&1 | Tee-Object -FilePath reindex-vision.log
```

### Option B — Manuellement, document par document

Pour réindexer un document précis :

```bash
uv run skills/ingest-doc/run.py "C:\chemin\document.docx" --vision --force
```

- `--vision` : active la description des images
- `--force` : force la ré-ingestion (sinon le doc est skippé comme doublon)

Le dédoublonnage intelligent purge l'ancienne version (doc + chunks) puis insère la nouvelle avec les descriptions d'images.

## 📊 Suivre l'avancement

Pendant la réindexation, ouvrir un **autre terminal** et vérifier l'état de la base :

```bash
uv run bench/check_status.py
```

Pour voir quels documents ont maintenant des descriptions d'images (chunks dont le texte contient des mots-clés typiques de description visuelle) :

```bash
uv run python -c "
import duckdb
con = duckdb.connect('knowledge.duckdb', read_only=True)
# Compter les chunks qui semblent issus de la vision (description d'image)
rows = con.execute(\"\"\"
  SELECT d.file_name, COUNT(*) AS nb_desc
  FROM chunks c JOIN documents d ON c.document_id = d.id
  WHERE c.text ILIKE '%capture%' OR c.text ILIKE '%bouton%'
     OR c.text ILIKE '%fenetre%' OR c.text ILIKE '%ecran%'
     OR c.text ILIKE '%interface%' OR c.text ILIKE '%schema%'
  GROUP BY d.file_name ORDER BY nb_desc DESC LIMIT 20
\"\"\").fetchall()
print(f'Documents avec chunks de description visuelle: {len(rows)}')
for name, n in rows:
    print(f'  {n:3d} | {name[:60]}')
con.close()
"
```

## 🔧 Que faire si la réindexation bloque ?

### Problème : un document met trop de temps
Le script a un timeout de sécurité de **15 minutes par document**. Si un doc dépasse, il est skippé et le script continue.

### Problème : Ollama ne répond plus
Vérifier l'état :
```bash
curl http://localhost:11434/api/tags
```
Si down, redémarrer Ollama puis relancer le script (reprise automatique).

### Problème : base verrouillée
Si un processus Python zombie détient la base :
```powershell
Get-Process python -ErrorAction SilentlyContinue
# Si des processus trainent, les tuer :
Get-Process python | Stop-Process -Force
```
Puis relancer le script.

## ⏱️ Estimations de durée

| Volume | Images/doc (moy.) | Temps total estimé |
|---|---|---|
| 169 docs (DOCX+PDF) | ~3-5 | **2-4 heures** |
| 147 DOCX seulement | ~3-5 | ~1h30-3h |
| 22 PDF seulement | ~2-4 | ~30 min-1h |
| Test (3 docs) | ~3 | ~5-10 min |

*Estimations basées sur ~15-30s par image via Gemma 4 E4B en local.*

## 📝 Après la réindexation

Une fois terminée, les captures d'écran sont désormais **recherchables**. Par exemple, une question sur "comment configurer le pare-feu" pourra trouver la réponse dans une capture d'écran qui montre l'interface de configuration, même si le texte autour ne mentionnait pas explicitement ces détails.

Vérifier la qualité avec le benchmark :
```bash
uv run bench/run_bench_chunks.py
uv run bench/compare_bench.py
```

---

*Documentation créée le 2026-07-25. Script : `skills/reindex-vision/run.py`.*
