#!/usr/bin/env python3
"""Génère le tableau de bord Home Assistant « Compteur d'eau » avec une vue par voisin déclaré.

Le script lit :
  - compteur-eau-lora.yaml : nom de l'appareil et voisins déclarés dans « packages: »
    (modèle voisins/voisin.yaml, inclus localement ou depuis GitHub) ;
  - secrets.yaml : valeurs des « !secret » (noms des voisins) ;
  - ha_dashboard_compteur_eau.yaml : vue de base (ton compteur).

Il écrit ha_dashboard_compteur_eau.genere.yaml (ignoré par git : il contient les noms
des voisins), à coller dans Home Assistant (crayon > ⋮ > Éditeur de configuration brute).

Utilisation (depuis la racine du dépôt, à côté de ton secrets.yaml) :
    uv run --with pyyaml python scripts/generer_tableau_de_bord.py
ou  pip install pyyaml && python3 scripts/generer_tableau_de_bord.py
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML manquant : « pip install pyyaml » ou « uv run --with pyyaml python … »")

MODELE_VOISIN = "voisins/voisin.yaml"


# ───────────────────────────── Lecture du YAML ESPHome ─────────────────────────────

class Include:
    """Valeur d'un « !include » (fichier + variables), sans charger le fichier."""

    def __init__(self, fichier: str, variables: dict | None = None):
        self.fichier = fichier
        self.variables = variables or {}


def chargeur(secrets: dict) -> type:
    class Chargeur(yaml.SafeLoader):
        pass

    def secret(loader, node):
        cle = loader.construct_scalar(node)
        if cle not in secrets:
            sys.exit(f"Secret « {cle} » absent de secrets.yaml")
        return secrets[cle]

    def include(loader, node):
        if isinstance(node, yaml.MappingNode):
            m = loader.construct_mapping(node, deep=True)
            return Include(str(m.get("file", "")), m.get("vars"))
        return Include(loader.construct_scalar(node))

    def autre(loader, suffixe, node):
        # !lambda, !extend, !remove… : valeur brute (inutile ici)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node, deep=True)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node, deep=True)
        return loader.construct_scalar(node)

    Chargeur.add_constructor("!secret", secret)
    Chargeur.add_constructor("!include", include)
    Chargeur.add_multi_constructor("!", autre)
    return Chargeur


def lire_yaml(chemin: Path, secrets: dict | None = None):
    with chemin.open(encoding="utf-8") as f:
        return yaml.load(f, Loader=chargeur(secrets or {}))


def substituer(valeur, subs: dict):
    """Remplace ${x} et $x par les substitutions de la configuration."""
    if not isinstance(valeur, str):
        return valeur
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: str(subs.get(m.group(1) or m.group(2), m.group(0))), valeur)


def voisins_declares(config: dict) -> list[dict]:
    """Liste des voisins {i, nom, num} déclarés dans « packages: », triée par i."""
    subs = config.get("substitutions") or {}
    trouves = []
    for cle, pkg in (config.get("packages") or {}).items():
        variables = None
        if isinstance(pkg, Include) and pkg.fichier.replace("\\", "/").endswith(MODELE_VOISIN):
            variables = pkg.variables
        elif isinstance(pkg, dict) and "files" in pkg:  # paquet distant (GitHub)
            for f in pkg["files"] or []:
                if isinstance(f, dict) and str(f.get("path", "")).endswith(MODELE_VOISIN):
                    variables = f.get("vars") or {}
        if variables is None:
            continue
        v = {k: substituer(val, subs) for k, val in variables.items()}
        if "i" not in v or "nom" not in v:
            sys.exit(f"Paquet « {cle} » : variables i et nom obligatoires")
        trouves.append({"i": int(v["i"]), "nom": str(v["nom"]), "num": str(v.get("num", ""))})
    numeros = [v["i"] for v in trouves]
    doublons = {i for i in numeros if numeros.count(i) > 1}
    if doublons:
        sys.exit(f"Numéro de voisin en double : {sorted(doublons)}")
    return sorted(trouves, key=lambda v: v["i"])


# ───────────────────────────── Identifiants Home Assistant ─────────────────────────────

def slug(texte: str) -> str:
    """Équivalent de homeassistant.util.slugify (accents retirés, séparateur « _ »)."""
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")


def entite(domaine: str, appareil: str, nom: str) -> str:
    return f"{domaine}.{slug(appareil + ' ' + nom)}"


# ───────────────────────────── Vue « Voisins » ─────────────────────────────

def vue_voisins(voisins: list[dict], appareil: str) -> dict:
    if not voisins:
        return {
            "title": "Voisins", "path": "voisins", "icon": "mdi:account-group", "type": "sections",
            "sections": [{"type": "grid", "cards": [{
                "type": "markdown",
                "content": "Aucun voisin déclaré dans `compteur-eau-lora.yaml` (voir README, « Voisins »).",
            }]}],
        }

    index_moi = entite("sensor", appareil, "Compteur eau - Volume total")
    tous = {
        "type": "grid",
        "column_span": 3,
        "cards": [
            {"type": "heading", "heading": "Tous les compteurs", "icon": "mdi:account-group"},
            {
                # Conso par jour = variation de l'index sur chaque journée (« change »)
                "type": "statistics-graph",
                "title": "Conso journalière (30 jours)",
                "chart_type": "bar",
                "period": "day",
                "days_to_show": 30,
                "stat_types": ["change"],
                "entities": [{"entity": index_moi, "name": "Moi"}] + [
                    {"entity": entite("sensor", appareil, f"{v['nom']} - Index"), "name": v["nom"]}
                    for v in voisins
                ],
            },
            {
                "type": "history-graph",
                "title": "Signal radio des compteurs (24 h)",
                "hours_to_show": 24,
                "entities": [{"entity": entite("sensor", appareil, "Compteur eau - RSSI"), "name": "Moi"}] + [
                    {"entity": entite("sensor", appareil, f"{v['nom']} - RSSI"), "name": v["nom"]}
                    for v in voisins
                ],
            },
        ],
    }

    sections = [tous]
    for v in voisins:
        nom = v["nom"]
        index = entite("sensor", appareil, f"{nom} - Index")
        sections.append({
            "type": "grid",
            "cards": [
                {"type": "heading", "heading": nom, "icon": "mdi:home-account"},
                {"type": "tile", "entity": index, "name": "Index", "icon": "mdi:counter", "vertical": True},
                {"type": "tile", "entity": entite("sensor", appareil, f"{nom} - Conso aujourd'hui"),
                 "name": "Aujourd'hui", "icon": "mdi:calendar-today", "vertical": True},
                {"type": "tile", "entity": entite("sensor", appareil, f"{nom} - RSSI"),
                 "name": "Signal radio", "icon": "mdi:radio-tower", "vertical": True},
                {
                    "type": "statistics-graph",
                    "title": "Conso journalière (30 jours)",
                    "chart_type": "bar",
                    "period": "day",
                    "days_to_show": 30,
                    "stat_types": ["change"],
                    "entities": [index],
                },
            ],
        })
    return {
        "title": "Voisins", "path": "voisins", "icon": "mdi:account-group",
        "type": "sections", "max_columns": 3, "sections": sections,
    }


# ───────────────────────────── Programme principal ─────────────────────────────

class Dumper(yaml.SafeDumper):
    """Listes indentées sous leur clé (même présentation que le fichier de base)."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def main() -> None:
    racine = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=racine / "compteur-eau-lora.yaml")
    ap.add_argument("--secrets", type=Path, help="défaut : secrets.yaml à côté de --config")
    ap.add_argument("--base", type=Path, default=racine / "ha_dashboard_compteur_eau.yaml")
    ap.add_argument("--sortie", type=Path, default=racine / "ha_dashboard_compteur_eau.genere.yaml")
    ap.add_argument("--appareil", help="nom de l'appareil dans HA (défaut : friendly_name de la configuration)")
    args = ap.parse_args()

    chemin_secrets = args.secrets or args.config.parent / "secrets.yaml"
    if not chemin_secrets.exists():
        sys.exit(f"{chemin_secrets} introuvable (copie secrets.example.yaml en secrets.yaml)")
    secrets = lire_yaml(chemin_secrets) or {}
    config = lire_yaml(args.config, secrets)

    esphome = config.get("esphome") or {}
    appareil = args.appareil or esphome.get("friendly_name") or esphome.get("name", "compteur-eau-lora")
    voisins = voisins_declares(config)

    tableau = lire_yaml(args.base)
    vues = [v for v in tableau.get("views", []) if v.get("path") != "voisins"]
    vues.append(vue_voisins(voisins, appareil))
    tableau["views"] = vues

    entete = (
        "# Tableau de bord GÉNÉRÉ par scripts/generer_tableau_de_bord.py : ne pas modifier à la main,\n"
        "# relancer le script après avoir ajouté ou retiré un voisin.\n"
        f"# Appareil : {appareil} | voisins : {', '.join(v['nom'] for v in voisins) or 'aucun'}\n"
    )
    texte = yaml.dump(tableau, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=1000)
    args.sortie.write_text(entete + texte, encoding="utf-8")
    print(f"{args.sortie.name} : {len(voisins)} voisin(s) ({', '.join(v['nom'] for v in voisins) or 'aucun'})")


if __name__ == "__main__":
    main()
