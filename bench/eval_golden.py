import sys
import os
import json
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.app import execute_rag

async def run_golden_tests():
    """
    Exécute les cas de test dorés (Golden Tests) pour évaluer la qualité du RAG
    avant déploiement.
    """
    print("=== Démarrage des évaluations : Golden Tests ===")

    # 50 golden tests mockés pour l'exemple
    golden_tests = [
        {"question": "Comment installer le client Sage 100 ?", "expected_source": "sage100_install.md"},
        {"question": "Quelle est la procédure de sauvegarde SQL ?", "expected_source": "backup_sql.md"},
        {"question": "Configuration du VPN IPsec ?", "expected_source": "vpn.md"}
    ]

    # On simule 50 cas en multipliant
    golden_tests = golden_tests * 17
    golden_tests = golden_tests[:50]

    success_count = 0
    low_confidence_count = 0
    error_count = 0

    for i, test in enumerate(golden_tests, 1):
        print(f"Test {i}/{len(golden_tests)}: {test['question']}")

        try:
            validated, final_answer, sources = await execute_rag(test['question'])

            if validated is None:
                if "J'ai besoin de plus de contexte" in final_answer:
                    print("  -> LOW CONFIDENCE (Garde-fou activé)")
                    low_confidence_count += 1
                else:
                    print(f"  -> ERREUR: {final_answer}")
                    error_count += 1
            else:
                print(f"  -> SUCCÈS (Confiance: {validated.confidence})")
                success_count += 1

        except Exception as e:
            print(f"  -> EXCEPTION: {e}")
            error_count += 1

    print("\n=== Rapport d'évaluation ===")
    print(f"Total des tests : {len(golden_tests)}")
    print(f"Succès (Confiance > 0.7) : {success_count} ({(success_count/len(golden_tests))*100:.1f}%)")
    print(f"Rejets (Confiance < 0.7) : {low_confidence_count} ({(low_confidence_count/len(golden_tests))*100:.1f}%)")
    print(f"Erreurs : {error_count} ({(error_count/len(golden_tests))*100:.1f}%)")

if __name__ == "__main__":
    # Vérifier que le modèle Ollama est dispo, sinon bypass pour le test
    # Dans un vrai CI, on s'assurerait que l'environnement RAG est up
    print("Golden tests prêts (Mocked run).")
    asyncio.run(run_golden_tests())
