"""Tests de ``scripts/ci_voisins.py`` (issue #48, couverture à 95 %).

Le script travaille sur des copies des vrais ``compteur-eau-lora.yaml`` et
``secrets.example.yaml``, dans un dossier temporaire passé en second argument :
rien n'est écrit dans le dépôt.
"""

from __future__ import annotations

import re
import runpy
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ci_voisins.py"


@pytest.fixture
def dossier(tmp_path: Path) -> Path:
    """Copie de la configuration principale et des secrets d'exemple."""
    for nom in ("compteur-eau-lora.yaml", "secrets.example.yaml"):
        shutil.copy(ROOT / nom, tmp_path / nom)
    return tmp_path


def _lancer(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *arguments])
    runpy.run_path(str(SCRIPT), run_name="__main__")


def _voisins(secrets: str) -> list[str]:
    return re.findall(r"^compteur([1-9]|10):", secrets, flags=re.MULTILINE)


def test_dix_voisins_et_entrees_facultatives(
    dossier: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """N = 10 : dix voisins de test, Izar, clés AES, typecompteurN et n° sans « 0x »."""
    _lancer(monkeypatch, "10", str(dossier))
    config = (dossier / "ci-voisins-10.yaml").read_text(encoding="utf-8")
    assert "  <<: !include ci-secrets-10.yaml\n" in config
    assert "<<: !include secrets.yaml" not in config
    # Paquet distant remplacé par les modèles locaux de la branche testée.
    assert "  voisins: !include voisins/voisins.yaml\n" in config
    assert "url: https://github.com/Mathilde-Team/Esphome-Compteur-wmbus" not in config

    secrets = (dossier / "ci-secrets-10.yaml").read_text(encoding="utf-8")
    assert _voisins(secrets) == [str(i) for i in range(1, 11)]
    assert 'compteur7: "10000007"\n' in secrets  # sans « 0x », nom par défaut
    assert "nomcompteur7" not in secrets
    assert 'nomcompteur1: "Test 1"\n' in secrets
    for ligne in ("type_compteur: izar\n", 'typecompteur2: "dme_07"\n', 'aesv4: ""\n'):
        assert ligne in secrets
    # Voisins d'exemple (Dupont…, y compris commentés) retirés avant les voisins de test.
    assert "Dupont" not in secrets
    assert "# compteur5" not in secrets
    assert 'compteur0: "0x12345678"' in secrets  # ton compteur conservé
    assert capsys.readouterr().out == "ci-voisins-10.yaml + ci-secrets-10.yaml : 10 voisin(s)\n"


def test_zero_voisin(dossier: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """N = 0 : aucun voisin, aucune entrée facultative de test."""
    _lancer(monkeypatch, "0", str(dossier))
    secrets = (dossier / "ci-secrets-0.yaml").read_text(encoding="utf-8")
    assert _voisins(secrets) == []
    assert "type_compteur: izar" not in secrets
    assert secrets.endswith("\n# ── CI ──\n")
    assert (dossier / "ci-voisins-0.yaml").exists()


def test_quelques_voisins_sans_entrees_facultatives(dossier: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """1 ≤ N < 10 : N voisins numérotés « 0x… », sans les entrées réservées à N = 10."""
    _lancer(monkeypatch, "3", str(dossier))
    secrets = (dossier / "ci-secrets-3.yaml").read_text(encoding="utf-8")
    assert _voisins(secrets) == ["1", "2", "3"]
    assert 'compteur3: "0x10000003"\n' in secrets
    assert not re.search(r"^(type_compteur|typecompteur\d+|aes\w*):", secrets, flags=re.MULTILINE)


def test_dossier_par_defaut_racine_du_depot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans second argument, le dossier est la racine du dépôt (fichiers ignorés par git)."""
    produits = [ROOT / "ci-voisins-2.yaml", ROOT / "ci-secrets-2.yaml"]
    avant = {p: p.read_bytes() for p in produits if p.exists()}
    try:
        _lancer(monkeypatch, "2")
        assert all(p.exists() for p in produits)
    finally:
        for p in produits:
            if p in avant:
                p.write_bytes(avant[p])
            else:
                p.unlink(missing_ok=True)


def test_n_par_defaut_dix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans argument, N vaut 10 (racine du dépôt, fichiers restaurés ensuite)."""
    produits = [ROOT / "ci-voisins-10.yaml", ROOT / "ci-secrets-10.yaml"]
    avant = {p: p.read_bytes() for p in produits if p.exists()}
    try:
        _lancer(monkeypatch)
        assert _voisins(produits[1].read_text(encoding="utf-8")) == [str(i) for i in range(1, 11)]
    finally:
        for p in produits:
            if p in avant:
                p.write_bytes(avant[p])
            else:
                p.unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("argument", "message"),
    [
        ("11", "N doit être compris entre 0 et 10"),
        ("-1", "N doit être un entier compris entre 0 et 10"),
        ("dix", "N doit être un entier compris entre 0 et 10"),
    ],
)
def test_n_invalide(dossier: Path, monkeypatch: pytest.MonkeyPatch, argument: str, message: str) -> None:
    """N hors de 0…10 ou non entier : refus explicite, rien n'est écrit."""
    with pytest.raises(SystemExit, match=message):
        _lancer(monkeypatch, argument, str(dossier))
    assert sorted(p.name for p in dossier.iterdir()) == ["compteur-eau-lora.yaml", "secrets.example.yaml"]


@pytest.mark.parametrize(
    ("ancien", "nouveau", "message"),
    [
        pytest.param(
            "  <<: !include secrets.yaml\n", "", "ligne « <<: !include secrets.yaml » introuvable", id="sans-fusion"
        ),
        pytest.param(
            "url: https://github.com/Mathilde-Team/Esphome-Compteur-wmbus\n",
            "url: https://exemple.invalid/fork\n",
            r"paquet « voisins » \(url GitHub\) introuvable",
            id="sans-paquet-distant",
        ),
    ],
)
def test_configuration_inattendue(
    dossier: Path, monkeypatch: pytest.MonkeyPatch, ancien: str, nouveau: str, message: str
) -> None:
    """Configuration sans fusion des secrets ou sans paquet voisins distant : refus explicite."""
    fichier = dossier / "compteur-eau-lora.yaml"
    texte = fichier.read_text(encoding="utf-8")
    assert ancien in texte
    fichier.write_text(texte.replace(ancien, nouveau, 1), encoding="utf-8")
    with pytest.raises(SystemExit, match=message):
        _lancer(monkeypatch, "10", str(dossier))
    assert not (dossier / "ci-voisins-10.yaml").exists()
