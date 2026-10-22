"""Les scripts lancés par les workflows reçoivent leurs dépendances.

Régression couverte : ``scripts/check_branch_protection.py`` importe loguru
(SOCLE §8) mais ``branch-protection.yml`` le lançait par
``uv run --no-project`` sans l'installer -> ``ModuleNotFoundError`` à chaque
push sur ``main``/``dev`` et chaque nuit.

Règle : toute commande ``uv run ... python scripts/<x>.py`` d'un workflow dont
le script importe loguru (analyse AST, aucun import du module) doit fournir
loguru : ``--with loguru==...``, ``--group scripts`` ou ``--only-group scripts``.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
COMMANDE = re.compile(r"uv run(?P<options>[^\n]*?)\spython\s+(?P<script>scripts/[\w./-]+\.py)")
FOURNIT_LOGURU = re.compile(r"--with[ =]loguru\b|--(?:only-)?group[ =]scripts\b")


def importe_loguru(script: Path) -> bool:
    """Vrai si le script importe loguru (``import loguru`` ou ``from loguru ...``)."""
    arbre = ast.parse(script.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import) and any(a.name.split(".")[0] == "loguru" for a in noeud.names):
            return True
        if isinstance(noeud, ast.ImportFrom) and (noeud.module or "").split(".")[0] == "loguru":
            return True
    return False


def commandes_run(valeur: object) -> list[str]:
    """Toutes les valeurs ``run:`` d'un workflow chargé (parcours récursif)."""
    trouvees: list[str] = []
    if isinstance(valeur, dict):
        for cle, sous in valeur.items():
            if cle == "run" and isinstance(sous, str):
                trouvees.append(sous)
            else:
                trouvees.extend(commandes_run(sous))
    elif isinstance(valeur, list):
        for sous in valeur:
            trouvees.extend(commandes_run(sous))
    return trouvees


def invocations() -> list[tuple[str, str, str]]:
    """(workflow, options uv, script) pour chaque ``uv run ... python scripts/x.py``."""
    resultat = []
    for fichier in sorted(WORKFLOWS.glob("*.yml")):
        contenu = yaml.safe_load(fichier.read_text(encoding="utf-8"))
        for run in commandes_run(contenu):
            for m in COMMANDE.finditer(run):
                resultat.append((fichier.name, m.group("options"), m.group("script")))
    return resultat


class TestDependancesDesWorkflows(unittest.TestCase):
    def test_des_invocations_sont_trouvees(self) -> None:
        # Garde-fou de la règle elle-même : un motif cassé ne vérifierait plus rien.
        scripts = {s for _, _, s in invocations()}
        self.assertIn("scripts/check_branch_protection.py", scripts)

    def test_scripts_loguru_lances_avec_loguru(self) -> None:
        manques = [
            f"{wf} : uv run{opts} python {script}"
            for wf, opts, script in invocations()
            if (ROOT / script).is_file() and importe_loguru(ROOT / script) and not FOURNIT_LOGURU.search(opts)
        ]
        self.assertEqual(manques, [], "scripts loguru lancés sans la dépendance :\n" + "\n".join(manques))

    def test_detection_import(self) -> None:
        self.assertTrue(importe_loguru(ROOT / "scripts" / "check_branch_protection.py"))
        self.assertFalse(importe_loguru(ROOT / "scripts" / "ci_voisins.py"))


if __name__ == "__main__":
    unittest.main()
