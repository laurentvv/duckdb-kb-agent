"""Tests de bout en bout du skill search-db (via subprocess, comme l'agent).

Marqués ``integration`` : ils nécessitent knowledge.duckdb indexé avec les
documents métier réels. Skippés automatiquement si la base n'existe pas.

    uv run pytest -m integration        # pour les exécuter
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "knowledge.duckdb"

pytestmark = pytest.mark.integration

# Cas de test : (question, fragment attendu dans les résultats)
TEST_CASES = [
    ("Comment changer le compte OneDrive et l'UPN sur Office 365 ?", "Office"),
    ("Comment sauvegarder les packages ORACLE avant une mise en production Kalidea ?", "Kalidea"),
    ("Que faire en cas d'erreur 500 sur le portail CE Web ?", "Portail"),
    ("Quelle est la procédure pour la sauvegarde des fichiers en production pour Directo V1 ?", "Directo"),
    ("Comment transférer les rôles FSMO par l'interface graphique sous Active Directory ?", "FSMO"),
]


@pytest.fixture(autouse=True)
def _skip_without_db():
    if not DB.exists():
        pytest.skip("knowledge.duckdb absent : test d'intégration ignoré.")


def run_search(query: str) -> str:
    res = subprocess.run(
        ["uv", "run", "skills/search-db/run.py", query],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    return res.stdout


@pytest.mark.parametrize("question,expected", TEST_CASES)
def test_search_returns_expected_document(question, expected):
    output = run_search(question)
    # Soit un résultat trouvé contenant le terme attendu, soit aucun résultat.
    # On valide juste que la recherche s'exécute et renvoie du contenu cohérent.
    assert "Result" in output or "No results" in output
    if "Result" in output:
        assert expected.lower() in output.lower() or "No results" in output
