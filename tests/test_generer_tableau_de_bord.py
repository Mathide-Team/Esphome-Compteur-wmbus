"""Tests de ``scripts/generer_tableau_de_bord.py`` (issue #48, couverture à 95 %).

Les tests de bout en bout utilisent les vrais fichiers du dépôt
(``compteur-eau-lora.yaml``, ``secrets.example.yaml``,
``ha_dashboard_compteur_eau.yaml``) ; la sortie est écrite dans un dossier
temporaire. Les fonctions sont aussi testées une à une sur des cas limites.
"""

from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "generer_tableau_de_bord.py"
CONFIG = ROOT / "compteur-eau-lora.yaml"
SECRETS = ROOT / "secrets.example.yaml"
BASE = ROOT / "ha_dashboard_compteur_eau.yaml"

_spec = importlib.util.spec_from_file_location("generer_tableau_de_bord", SCRIPT)
gtb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gtb)

APPAREIL = "Compteur Eau LoRa"


def _lancer(monkeypatch: pytest.MonkeyPatch, *arguments: str) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), *arguments])
    gtb.main()


def _vue(tableau: dict, chemin: str) -> dict:
    return next(v for v in tableau["views"] if v.get("path") == chemin)


# ───────────────────────────── Bout en bout ─────────────────────────────


def test_generation_depuis_les_fichiers_du_depot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Configuration réelle + secrets d'exemple : une section par voisin, en-tête complet."""
    sortie = tmp_path / "genere.yaml"
    _lancer(monkeypatch, "--secrets", str(SECRETS), "--sortie", str(sortie))

    texte = sortie.read_text(encoding="utf-8")
    assert texte.startswith("# Tableau de bord GÉNÉRÉ par scripts/generer_tableau_de_bord.py")
    assert f"# Appareil : {APPAREIL} | voisins : Dupont, Martin, Durand, Petit\n" in texte
    assert "# Jauges : seuil débit 1000 L/h, seuil jour 800 L | ntfy : non\n" in texte
    tableau = yaml.safe_load(texte)
    voisins = _vue(tableau, "voisins")
    titres = [s["cards"][0]["heading"] for s in voisins["sections"]]
    assert titres == ["Tous les compteurs", "Dupont", "Martin", "Durand", "Petit"]
    dupont = voisins["sections"][1]["cards"]
    assert dupont[1]["entity"] == "sensor.compteur_eau_lora_dupont_index"
    # Vue de base conservée, une seule vue « voisins ».
    assert _vue(tableau, "eau")
    assert [v.get("path") for v in tableau["views"]].count("voisins") == 1
    assert capsys.readouterr().out == "genere.yaml : 4 voisin(s) (Dupont, Martin, Durand, Petit)\n"


def test_listes_indentees_sous_leur_cle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le Dumper indente les listes sous leur clé, comme le fichier de base."""
    sortie = tmp_path / "genere.yaml"
    _lancer(monkeypatch, "--secrets", str(SECRETS), "--sortie", str(sortie))
    assert "\nviews:\n  - title:" in sortie.read_text(encoding="utf-8")


def test_seuils_en_option(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--seuil-debit et --seuil-jour priment sur la configuration et règlent les jauges."""
    sortie = tmp_path / "genere.yaml"
    _lancer(
        monkeypatch,
        "--secrets", str(SECRETS),
        "--sortie", str(sortie),
        "--seuil-debit", "500",
        "--seuil-jour", "400",
    )  # fmt: skip
    texte = sortie.read_text(encoding="utf-8")
    assert "seuil débit 500 L/h, seuil jour 400 L" in texte
    jauges = {c["entity"]: c for c in gtb.cartes(yaml.safe_load(texte)) if c.get("type") == "gauge"}
    debit = jauges["sensor.compteur_eau_lora_debit_estime"]
    assert debit["max"] == 750
    assert [s["from"] for s in debit["segments"]] == [0, 150, 500]
    jour = jauges["sensor.compteur_eau_lora_conso_aujourd_hui"]
    assert jour["max"] == 500
    assert [s["from"] for s in jour["segments"]] == [0, 250, 400]


def test_appareil_en_option(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--appareil (appareil renommé dans HA) : en-tête et entités de la vue Voisins suivent ce nom."""
    sortie = tmp_path / "genere.yaml"
    _lancer(monkeypatch, "--secrets", str(SECRETS), "--sortie", str(sortie), "--appareil", "Eau Garage")
    texte = sortie.read_text(encoding="utf-8")
    assert "# Appareil : Eau Garage |" in texte
    voisins = _vue(yaml.safe_load(texte), "voisins")
    assert voisins["sections"][1]["cards"][1]["entity"] == "sensor.eau_garage_dupont_index"


def _config_minimale(tmp_path: Path, packages: str, secrets: str, nombres: str = "") -> Path:
    dossier = tmp_path / "config"
    dossier.mkdir()
    (dossier / "secrets.yaml").write_text(secrets, encoding="utf-8")
    (dossier / "compteur-eau-lora.yaml").write_text(
        "substitutions:\n"
        "  <<: !include secrets.yaml\n"
        "  num_compteur: !secret compteur0\n"
        "esphome:\n"
        "  name: eau-cave\n"
        f"packages:\n{packages}"
        f"{nombres}",
        encoding="utf-8",
    )
    return dossier / "compteur-eau-lora.yaml"


def test_secrets_a_cote_de_la_config_ntfy_et_seuils_de_la_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans --secrets : secrets.yaml à côté de --config ; nom ESPHome, seuils et ntfy lus."""
    config = _config_minimale(
        tmp_path,
        "  ntfy: !include ntfy.yaml\n",
        'compteur0: "0x12345678"\n',
        "number:\n"
        "  - platform: template\n"
        "    id: seuil_debit_l_h\n"
        "    initial_value: 600\n"
        "  - platform: template\n"
        "    id: seuil_jour_l\n"
        "    initial_value: 300\n",
    )
    sortie = tmp_path / "genere.yaml"
    _lancer(monkeypatch, "--config", str(config), "--sortie", str(sortie))
    texte = sortie.read_text(encoding="utf-8")
    assert "# Appareil : eau-cave | voisins : aucun\n" in texte
    assert "# Jauges : seuil débit 600 L/h, seuil jour 300 L | ntfy : oui\n" in texte
    tableau = yaml.safe_load(texte)
    contenu = _vue(tableau, "voisins")["sections"][0]["cards"][0]["content"]
    assert contenu.startswith("Aucun voisin dans `secrets.yaml`")
    actions = [c for c in gtb.cartes(tableau) if c.get("title") == "Notifications ntfy"]
    assert len(actions) == 1
    assert actions[0]["entities"][0]["entity"] == "switch.eau_cave_ntfy_notifications_actives"


def test_secrets_introuvables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pas de secrets.yaml : message explicite invitant à copier l'exemple."""
    absent = tmp_path / "absent.yaml"
    with pytest.raises(SystemExit, match=r"absent\.yaml introuvable \(copie secrets\.example\.yaml"):
        _lancer(monkeypatch, "--secrets", str(absent), "--sortie", str(tmp_path / "x.yaml"))
    assert not (tmp_path / "x.yaml").exists()


def test_secret_absent_de_secrets_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un « !secret » inconnu arrête la génération en nommant le secret (pas sa valeur)."""
    config = _config_minimale(tmp_path, "  ntfy: !include ntfy.yaml\n", 'autre: "x"\n')
    with pytest.raises(SystemExit, match="Secret « compteur0 » absent de secrets.yaml"):
        _lancer(monkeypatch, "--config", str(config), "--sortie", str(tmp_path / "x.yaml"))


def test_lancement_direct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``python scripts/generer_tableau_de_bord.py`` (comme en CI) écrit le tableau."""
    sortie = tmp_path / "genere.yaml"
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--secrets", str(SECRETS), "--sortie", str(sortie)])
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert sortie.exists()


# ───────────────────────────── Lecture du YAML ESPHome ─────────────────────────────


def test_chargeur_balises_esphome() -> None:
    """!include (simple ou avec variables), !secret et autres balises ESPHome sont lus."""
    texte = (
        "a: !include fichier.yaml\n"
        "b: !include {file: voisins/voisin.yaml, vars: {i: 1, nom: X}}\n"
        "c: !secret cle\n"
        "d: !lambda return 1;\n"
        "e: !extend {id: x}\n"
        "f: !remove [1, 2]\n"
    )
    document = yaml.load(texte, Loader=gtb.chargeur({"cle": "valeur"}))  # chargeur dérivé de SafeLoader
    assert isinstance(document["a"], gtb.Include)
    assert (document["a"].fichier, document["a"].variables) == ("fichier.yaml", {})
    assert (document["b"].fichier, document["b"].variables) == ("voisins/voisin.yaml", {"i": 1, "nom": "X"})
    assert document["c"] == "valeur"
    assert document["d"] == "return 1;"
    assert document["e"] == {"id": "x"}
    assert document["f"] == [1, 2]


def test_lire_yaml_ignore_la_fusion_de_fichier(tmp_path: Path) -> None:
    """« <<: !include secrets.yaml » (non géré par PyYAML) est retiré avant lecture."""
    fichier = tmp_path / "c.yaml"
    fichier.write_text("substitutions:\n  <<: !include secrets.yaml  # fusion\n  x: 1\n", encoding="utf-8")
    assert gtb.lire_yaml(fichier) == {"substitutions": {"x": 1}}


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (3, 3),
        (None, None),
        ("${num}-$nom", "0x1-Dupont"),
        ("$inconnu et ${absent}", "$inconnu et ${absent}"),
    ],
)
def test_substituer(valeur: object, attendu: object) -> None:
    """${x} et $x remplacés ; inconnus et non-textes laissés tels quels."""
    assert gtb.substituer(valeur, {"num": "0x1", "nom": "Dupont"}) == attendu


def test_voisins_de_secrets() -> None:
    """compteurN présent et non vide (1 à 10) ; nom par défaut « Voisin N »."""
    secrets = {
        "compteur0": "0x1",
        "compteur1": "0x2",
        "nomcompteur1": "Dupont",
        "compteur2": "",
        "compteur3": 345,
        "nomcompteur3": "",
        "compteur10": "0x10",
        "compteur11": "0x11",
    }
    assert gtb.voisins_de_secrets(secrets) == [
        {"i": 1, "nom": "Dupont", "num": "0x2"},
        {"i": 3, "nom": "Voisin 3", "num": "345"},
        {"i": 10, "nom": "Voisin 10", "num": "0x10"},
    ]


@pytest.mark.parametrize(
    ("paquet", "attendu"),
    [
        pytest.param("INCLUDE", [("voisins/voisin.yaml", {"i": 2})], id="include-local"),
        pytest.param(
            {"url": "https://exemple.invalid", "files": [{"path": "voisins/voisin.yaml", "vars": {"i": 1}},
                                                         "voisins/voisins.yaml", {"path": "x.yaml"}]},
            [("voisins/voisin.yaml", {"i": 1}), ("voisins/voisins.yaml", None), ("x.yaml", {})],
            id="distant-fichiers",
        ),
        pytest.param({"url": "https://exemple.invalid", "files": None}, [], id="distant-sans-fichier"),
        pytest.param("github://Mathilde-Team/x/ntfy.yaml@main", [("github://Mathilde-Team/x/ntfy.yaml", None)],
                     id="github"),
        pytest.param("autre chose", [], id="inconnu"),
        pytest.param(None, [], id="vide"),
    ],
)  # fmt: skip
def test_chemins_paquet(paquet: object, attendu: list) -> None:
    """Chemins d'un paquet local, distant (url + files), github:// ; rien sinon."""
    if paquet == "INCLUDE":
        paquet = gtb.Include("voisins\\voisin.yaml", {"i": 2})  # séparateur Windows normalisé
    assert gtb.chemins_paquet(paquet) == attendu


def test_voisins_declares_auto_et_manuels() -> None:
    """Voisins de secrets.yaml et voisins manuels réunis, triés par numéro, substitutions appliquées."""
    config = {
        "substitutions": {"nom5": "Lefèvre"},
        "packages": {
            "voisins": {"url": "https://exemple.invalid", "files": ["voisins/voisins.yaml"]},
            "voisin5": gtb.Include("voisins/voisin.yaml", {"i": "5", "nom": "${nom5}", "num": "0x5"}),
            "voisin6": gtb.Include("voisins/voisin.yaml", {"i": 6, "nom": "Sans numéro"}),
            "ntfy": gtb.Include("ntfy.yaml"),
        },
    }
    voisins = gtb.voisins_declares(config, {"compteur2": "0x2", "nomcompteur2": "Martin"})
    assert voisins == [
        {"i": 2, "nom": "Martin", "num": "0x2"},
        {"i": 5, "nom": "Lefèvre", "num": "0x5"},
        {"i": 6, "nom": "Sans numéro", "num": ""},
    ]


def test_voisins_declares_sans_paquets_ni_secrets() -> None:
    """Ni paquets ni secrets : aucun voisin (pas d'exception)."""
    assert gtb.voisins_declares({"packages": None}) == []
    assert gtb.voisins_declares({"packages": {"v": {"files": ["voisins/voisins.yaml"]}}}) == []


def test_voisin_en_double() -> None:
    """Même numéro déclaré deux fois (secrets + manuel) : refus explicite."""
    config = {
        "packages": {
            "voisins": {"files": ["voisins/voisins.yaml"]},
            "voisin1": gtb.Include("voisins/voisin.yaml", {"i": 1, "nom": "Doublon"}),
        }
    }
    with pytest.raises(SystemExit, match=r"Numéro de voisin en double : \[1\]"):
        gtb.voisins_declares(config, {"compteur1": "0x1"})


@pytest.mark.parametrize("variables", [{"nom": "Sans i"}, {"i": 3}, {}])
def test_voisin_manuel_incomplet(variables: dict) -> None:
    """Voisin manuel sans i ou sans nom : refus qui nomme le paquet."""
    with pytest.raises(SystemExit, match="Paquet « voisin3 » : variables i et nom obligatoires"):
        gtb.voisin_manuel("voisin3", variables, {})


# ───────────────────────────── Identifiants et cartes ─────────────────────────────


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Compteur Eau LoRa Débit estimé", "compteur_eau_lora_debit_estime"),
        ("Conso aujourd'hui", "conso_aujourd_hui"),
        ("  --Élan  Œuvre--  ", "elan_uvre"),
    ],
)
def test_slug(texte: str, attendu: str) -> None:
    """Comme homeassistant.util.slugify : accents retirés, séparateur « _ »."""
    assert gtb.slug(texte) == attendu


def test_valeur_initiale() -> None:
    """Valeur initiale d'un « number » par id ; None si absent ou sans valeur."""
    config = {"number": ["texte", {"id": "a"}, {"id": "b", "initial_value": "12.5"}]}
    assert gtb.valeur_initiale(config, "b") == 12.5
    assert gtb.valeur_initiale(config, "a") is None
    assert gtb.valeur_initiale({"number": None}, "b") is None


def test_regler_jauges_seulement_les_jauges_visees() -> None:
    """Seules les jauges de débit et de conso du jour sont réglées."""
    debit = {"type": "gauge", "entity": "sensor.eau_debit_estime"}
    jour = {"type": "gauge", "entity": "sensor.eau_conso_aujourd_hui"}
    autre_jauge = {"type": "gauge", "entity": "sensor.eau_rssi", "max": 0}
    tuile = {"type": "tile", "entity": "sensor.eau_debit_estime"}
    tableau = {"views": [{"sections": [{"cards": [debit, jour, autre_jauge, tuile]}, {}]}, {}]}
    gtb.regler_jauges(tableau, "Eau", 1000, 800)
    assert debit["max"] == 1500
    assert [s["from"] for s in debit["segments"]] == [0, 300, 1000]
    assert jour["max"] == 1000
    assert [s["from"] for s in jour["segments"]] == [0, 500, 800]
    assert autre_jauge == {"type": "gauge", "entity": "sensor.eau_rssi", "max": 0}
    assert "max" not in tuile


@pytest.mark.parametrize(
    ("paquets", "attendu"),
    [
        pytest.param({"ntfy": "github://Mathilde-Team/Esphome-Compteur-wmbus-ntfy/ntfy.yaml@main"}, True,
                     id="distant"),
        pytest.param({"ntfy": "INCLUDE"}, True, id="local"),
        pytest.param({"ntfy": {"url": "https://exemple.invalid", "files": ["ntfy.yaml"]}}, True, id="fichiers"),
        pytest.param({"voisins": {"url": "https://exemple.invalid", "files": None}}, False, id="sans-fichier"),
        pytest.param({"voisins": "github://x/voisins.yaml"}, False, id="autre"),
        pytest.param(None, False, id="aucun"),
    ],
)  # fmt: skip
def test_paquet_ntfy(paquets: dict | None, attendu: bool) -> None:
    """Paquet ntfy détecté qu'il soit distant, local ou listé dans files."""
    if paquets and paquets.get("ntfy") == "INCLUDE":
        paquets = {"ntfy": gtb.Include("paquets/ntfy.yaml")}
    assert gtb.paquet_ntfy({"packages": paquets}) is attendu


def test_actions_ntfy_sans_section_actions() -> None:
    """Sans section « Actions », le tableau n'est pas modifié."""
    tableau = {"views": [{"sections": [{"cards": [{"type": "heading", "heading": "Autre"}]}]}]}
    gtb.ajouter_actions_ntfy(tableau, "Eau")
    assert tableau == {"views": [{"sections": [{"cards": [{"type": "heading", "heading": "Autre"}]}]}]}


def test_actions_ntfy_une_seule_fois() -> None:
    """Les boutons ntfy vont dans la première section « Actions » seulement."""
    actions = {"cards": [{"type": "heading", "heading": "Actions"}]}
    seconde = {"cards": [{"type": "heading", "heading": "Actions"}]}
    tableau = {"views": [{"sections": [actions]}, {"sections": [seconde]}]}
    gtb.ajouter_actions_ntfy(tableau, "Eau")
    assert [c.get("title") for c in actions["cards"]] == [None, "Notifications ntfy"]
    assert len(seconde["cards"]) == 1
