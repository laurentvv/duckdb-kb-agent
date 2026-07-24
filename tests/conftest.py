"""Configuration pytest : permet d'importer les skills (scripts run.py) comme modules.

Les skills sont des scripts exécutables avec un bloc ``if __name__ == "__main__"``,
donc leur import est sûr. ``load_skill`` renvoie le module chargé en mémoire.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"


def load_skill(name: str):
    """Charge et retourne le module d'un skill donné (ex: 'ingest-doc')."""
    path = SKILLS / name / "run.py"
    spec = importlib.util.spec_from_file_location(f"skill_{name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
