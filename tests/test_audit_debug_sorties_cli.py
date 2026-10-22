"""Lancement en ligne de commande de ``scripts/audit_debug_sorties.py`` (issue #48).

Les fonctions de l'audit sont testées par ``test_loguru_regles.py`` ; ici,
seul le point d'entrée ``python scripts/audit_debug_sorties.py`` : il doit
sortir avec le code 0 et afficher le total rapporté à la référence.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_debug_sorties.py"


def test_lancement_direct(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """``python scripts/audit_debug_sorties.py`` : rapport et code de retour 0."""
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    with pytest.raises(SystemExit) as sortie:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert sortie.value.code == 0
    lignes = (ROOT / "scripts" / "audit_debug_sorties.baseline").read_text(encoding="utf-8").splitlines()
    reference = next(ligne for ligne in lignes if ligne and not ligne.startswith("#"))
    rapport = capsys.readouterr().out
    assert rapport.startswith("0 fonction(s) sans debug() en entrée ou à chaque sortie")
    assert f"(référence : {reference})" in rapport
