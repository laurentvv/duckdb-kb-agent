"""Agrège scores.jsonl + results.jsonl -> bench/REPORT.md (rapport final).

Usage :
  uv run bench/make_report.py
"""

import json
from collections import defaultdict
from pathlib import Path

BENCH = Path(__file__).parent
RESULTS = BENCH / "results.jsonl"
SCORES = BENCH / "scores.jsonl"
REPORT = BENCH / "REPORT.md"

CRITERIA = [("F", "Fidélité"), ("P", "Précision"), ("C", "Complétude"), ("H", "anti-Halluc.")]


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    results = load_jsonl(RESULTS)
    scores = {s["id"]: s for s in load_jsonl(SCORES)}

    # Indexer résultats : id -> model -> run
    by_id = defaultdict(dict)
    for r in results:
        key = "gemma" if "gemma" in r["model"] else "lfm"
        by_id[r["id"]][key] = r

    # Agrégation
    totals = {"gemma": {"score": 0, "max": 0, "lat": [], "tok": []},
              "lfm":   {"score": 0, "max": 0, "lat": [], "tok": []}}
    rows = []
    for qid in sorted(scores):
        s = scores[qid]
        for m in ("gemma", "lfm"):
            sc = s[m]
            sub = sum(sc[k] for k, _ in CRITERIA)
            run = by_id[qid][m]
            totals[m]["score"] += sub
            totals[m]["max"] += 8
            totals[m]["lat"].append(run["elapsed_s"])
            if run.get("tokens"):
                totals[m]["tok"].append(run["tokens"])
        rows.append((qid, scores[qid], by_id[qid]))

    # Scores finaux /10
    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    score10 = {
        "gemma": totals["gemma"]["score"] / totals["gemma"]["max"] * 10,
        "lfm": totals["lfm"]["score"] / totals["lfm"]["max"] * 10,
    }

    # --- Rédaction REPORT.md
    L = []
    L.append("# 📊 Benchmark RAG : Gemma-4-E4B vs LFM2.5\n")
    L.append("Comparaison de deux modèles LLM sur 20 questions factuelles posées à la base documentaire "
             "(pipeline RAG identique : FTS top-3 → contexte commun → réponse).\n")
    L.append("**Date** : 2026-07-16  |  **Corpus** : knowledge.duckdb (237 docs)  |  **Température** : 0.1\n")
    L.append("**Modèles** :")
    L.append("- `hf.co/unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL` (Gemma-4-E4B, 7.5B)")
    L.append("- `lfm2.5:latest` (LFM2.5, 8.5B MoE)\n")

    # --- Tableau récap
    L.append("## 🏆 Score final\n")
    L.append("| Modèle | Score /10 | Fidélité | Précision | Complétude | Anti-halluc. | Latence moy. (s) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for m, name in [("gemma", "Gemma-4-E4B"), ("lfm", "LFM2.5")]:
        t = totals[m]
        per_crit = {k: sum(scores[q][m][k] for q in scores) for k, _ in CRITERIA}
        max_crit = {k: 2 * len(scores) for k, _ in CRITERIA}
        crit_str = " | ".join(f"{per_crit[k]}/{max_crit[k]}" for k, _ in CRITERIA)
        L.append(f"| **{name}** | **{score10[m]:.1f}** | {crit_str} | {avg(t['lat']):.1f} |")
    L.append("")

    # --- Détail question par question
    L.append("## 📝 Détail par question\n")
    L.append("Critères notés sur 2 chacun (total /8 par réponse) : **F**=Fidélité au contexte, "
             "**P**=Précision, **C**=Complétude, **H**=anti-Hallucination.\n")
    for qid, sc, runs in rows:
        L.append(f"### Q{qid} — {runs['gemma']['question']}")
        L.append(f"*Thème : {runs['gemma']['theme']}  ·  Doc attendu : `{runs['gemma']['expected_doc_hint']}`*\n")
        for m, name in [("gemma", "Gemma-4-E4B"), ("lfm", "LFM2.5")]:
            s = sc[m]
            sub = sum(s[k] for k, _ in CRITERIA)
            run = runs[m]
            crit = " ".join(f"{k}={s[k]}" for k, _ in CRITERIA)
            L.append(f"**{name}** — {sub}/8 ({crit}) · {run['elapsed_s']}s")
            L.append("")
            ans = run["answer"].strip()
            L.append(f"> {ans[:600]}{'…' if len(ans) > 600 else ''}")
            L.append("")
        L.append(f"*Note du juge : {sc['note']}*\n")
        L.append("---\n")

    # --- Analyse qualitative
    L.append("## 🔍 Analyse qualitative\n")
    L.append("### Forces / faiblesses\n")
    L.append("**Gemma-4-E4B** :")
    L.append("- ✅ Réponses exhaustives et bien structurées (étapes complètes).")
    L.append("- ✅ Discipline exemplaire anti-hallucination : dit explicitement quand le contexte manque (Q13).")
    L.append("- ✅ Reste fidèlement en français.")
    L.append("- ⚠️ Plus lent en moyenne.")
    L.append("")
    L.append("**LFM2.5** :")
    L.append("- ✅ Plus rapide (latence plus faible).")
    L.append("- ✅ Souvent correct sur les questions simples.")
    L.append("- ❌ Hallucinations (Q13 : invente une raison non documentée).")
    L.append("- ❌ Échecs purs de lecture du contexte (Q6 : nie l'existence d'un préfixe pourtant présent).")
    L.append("- ❌ Instabilité linguistique : répond en anglais sur 2 questions posées en français (Q3, Q15).")
    L.append("- ❌ Erreurs techniques subtiles (Q12 : confond `delete-keys` et `delete-secret-keys`).")
    L.append("")

    # --- Recommandation
    winner = "Gemma-4-E4B" if score10["gemma"] >= score10["lfm"] else "LFM2.5"
    L.append("## ✅ Recommandation\n")
    L.append(f"**{winner}** remporte ce benchmark ({max(score10['gemma'], score10['lfm']):.1f}/10 "
             f"contre {min(score10['gemma'], score10['lfm']):.1f}/10). ")
    L.append("\nPour un usage de **base de connaissances technique en français**, Gemma-4-E4B est nettement "
             "préférable : moins d'hallucinations, aucune dérive linguistique, réponses plus complètes. "
             "LFM2.5 peut convenir pour des questions simples où la latence compte, mais sa propension à "
             "halluciner et à répondre en anglais le rend risqué pour un assistant d'exploitation.\n")

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"Rapport écrit : {REPORT}")
    print(f"\nScore final : Gemma-4-E4B {score10['gemma']:.1f}/10  |  LFM2.5 {score10['lfm']:.1f}/10")


if __name__ == "__main__":
    main()
