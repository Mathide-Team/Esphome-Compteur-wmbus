#!/usr/bin/env python3
"""Génère le tableau de bord Home Assistant « Compteur d'eau » avec une vue par voisin déclaré.

Le script lit :
  - compteur-eau-lora.yaml : nom de l'appareil et paquets inclus ;
  - secrets.yaml : voisins (compteur1 … compteur10, nomcompteurN) si voisins/voisins.yaml est
    inclus, et valeurs des « !secret » des voisins déclarés à la main (voisins/voisin.yaml) ;
  - ha_dashboard_compteur_eau.yaml : vue de base (ton compteur).

Il règle aussi les jauges sur les seuils d'alerte (valeurs initiales de la configuration, ou
--seuil-debit / --seuil-jour) et ajoute les boutons ntfy si ce paquet est inclus.

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

from loguru import logger

try:
    import yaml
except ImportError:  # pragma: no cover
    from loguru import logger  # noqa: F401 — dernier recours, PyYAML absent

    logger.critical("PyYAML manquant : « pip install pyyaml » ou « uv run --with pyyaml python … »")
    sys.exit("PyYAML manquant : « pip install pyyaml » ou « uv run --with pyyaml python … »")

MODELE_VOISIN = "voisins/voisin.yaml"
VOISINS_AUTO = "voisins/voisins.yaml"   # voisins déduits de secrets.yaml
FUSION_INCLUDE = re.compile(r"^[ \t]*<<:[ \t]*!include[ \t]+\S+[ \t]*(#.*)?\n", re.M)


# ───────────────────────────── Lecture du YAML ESPHome ─────────────────────────────

class Include:
    """Valeur d'un « !include » (fichier + variables), sans charger le fichier."""

    def __init__(self, fichier: str, variables: dict | None = None):
        logger.debug("Include.__init__() appelée | fichier={}", fichier)
        self.fichier = fichier
        self.variables = variables or {}
        logger.debug("Include.__init__() retourne | include prêt")


def chargeur(secrets: dict) -> type:
    logger.debug("chargeur() appelée | {} secret(s)", len(secrets))
    class Chargeur(yaml.SafeLoader):
        pass

    def secret(loader, node):
        logger.debug("secret() appelée | lecture d'un !secret")
        cle = loader.construct_scalar(node)
        if cle not in secrets:
            logger.error("secret() : secret absent de secrets.yaml (valeur non journalisée)")
            sys.exit(f"Secret « {cle} » absent de secrets.yaml")
        logger.debug("secret() retourne | valeur substituée (jamais journalisée)")
        return secrets[cle]

    def include(loader, node):
        logger.debug("include() appelée | lecture d'un !include")
        if isinstance(node, yaml.MappingNode):
            m = loader.construct_mapping(node, deep=True)
            logger.debug("include() retourne | include avec variables")
            return Include(str(m.get("file", "")), m.get("vars"))
        logger.debug("include() retourne | include simple")
        return Include(loader.construct_scalar(node))

    def autre(loader, suffixe, node):
        # !lambda, !extend, !remove… : valeur brute (inutile ici)
        logger.debug("autre() appelée | constructeur !{}", suffixe)
        if isinstance(node, yaml.MappingNode):
            logger.debug("autre() retourne | mapping brut")
            return loader.construct_mapping(node, deep=True)
        if isinstance(node, yaml.SequenceNode):
            logger.debug("autre() retourne | séquence brute")
            return loader.construct_sequence(node, deep=True)
        logger.debug("autre() retourne | scalaire brut")
        return loader.construct_scalar(node)

    Chargeur.add_constructor("!secret", secret)
    Chargeur.add_constructor("!include", include)
    Chargeur.add_multi_constructor("!", autre)
    logger.debug("chargeur() retourne | chargeur YAML prêt")
    return Chargeur


def lire_yaml(chemin: Path, secrets: dict | None = None):
    logger.debug("lire_yaml() appelée | chemin={}", chemin.name)
    texte = chemin.read_text(encoding="utf-8")
    # « <<: !include secrets.yaml » (fusion YAML d'un fichier) : non géré par PyYAML, inutile ici
    texte = FUSION_INCLUDE.sub("", texte)
    document = yaml.load(texte, Loader=chargeur(secrets or {}))
    logger.debug("lire_yaml() retourne | document chargé")
    return document


def substituer(valeur, subs: dict):
    """Remplace ${x} et $x par les substitutions de la configuration."""
    logger.debug("substituer() appelée")
    if not isinstance(valeur, str):
        logger.debug("substituer() retourne | valeur non textuelle inchangée")
        return valeur
    resultat = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: str(subs.get(m.group(1) or m.group(2), m.group(0))), valeur)
    logger.debug("substituer() retourne | substitutions appliquées")
    return resultat


def voisins_de_secrets(secrets: dict) -> list[dict]:
    """Voisins de voisins/voisins.yaml : « compteurN » présent et non vide (N = 1 à 10)."""
    return [
        {"i": i, "nom": str(secrets.get(f"nomcompteur{i}") or f"Voisin {i}"), "num": str(secrets[f"compteur{i}"])}
        for i in range(1, 11)
        if secrets.get(f"compteur{i}") not in (None, "")
    ]


def chemins_paquet(pkg) -> list[tuple[str, dict | None]]:
    """(fichier, variables) d'un paquet : !include local, ou paquet distant (url + files)."""
    logger.debug("chemins_paquet() appelée")
    if isinstance(pkg, Include):
        logger.debug("chemins_paquet() retourne | paquet local")
        return [(pkg.fichier.replace("\\", "/"), pkg.variables)]
    if isinstance(pkg, dict) and "files" in pkg:
        chemins = [
            (str(f.get("path", "")), f.get("vars") or {}) if isinstance(f, dict) else (str(f), None)
            for f in pkg["files"] or []
        ]
        logger.debug("chemins_paquet() retourne | {} fichier(s) distant(s)", len(chemins))
        return chemins
    if isinstance(pkg, str) and pkg.startswith("github://"):
        logger.debug("chemins_paquet() retourne | paquet distant")
        return [(pkg.split("@")[0], None)]
    logger.debug("chemins_paquet() retourne | aucun chemin")
    return []


def voisins_declares(config: dict, secrets: dict | None = None) -> list[dict]:
    """Liste des voisins {i, nom, num} : déduits de secrets.yaml et/ou déclarés à la main."""
    logger.debug("voisins_declares() appelée")
    subs = config.get("substitutions") or {}
    trouves = []
    for cle, pkg in (config.get("packages") or {}).items():
        for fichier, variables in chemins_paquet(pkg):
            if fichier.endswith(VOISINS_AUTO):
                trouves += voisins_de_secrets(secrets or {})
            elif fichier.endswith(MODELE_VOISIN):
                trouves.append(voisin_manuel(cle, variables or {}, subs))
    numeros = [v["i"] for v in trouves]
    doublons = {i for i in numeros if numeros.count(i) > 1}
    if doublons:
        logger.error("voisins_declares() : numéro de voisin en double {}", sorted(doublons))
        sys.exit(f"Numéro de voisin en double : {sorted(doublons)}")
    logger.debug("voisins_declares() retourne | {} voisin(s)", len(trouves))
    return sorted(trouves, key=lambda v: v["i"])


def voisin_manuel(cle: str, variables: dict, subs: dict) -> dict:
    """Voisin déclaré par une ligne « voisinN: !include { file: voisins/voisin.yaml, vars: … } »."""
    logger.debug("voisin_manuel() appelée | paquet={}", cle)
    v = {k: substituer(val, subs) for k, val in variables.items()}
    if "i" not in v or "nom" not in v:
        logger.error("voisin_manuel() : variables i et nom obligatoires (paquet {})", cle)
        sys.exit(f"Paquet « {cle} » : variables i et nom obligatoires")
    voisin = {"i": int(v["i"]), "nom": str(v["nom"]), "num": str(v.get("num", ""))}
    logger.debug("voisin_manuel() retourne | voisin n°{}", voisin["i"])
    return voisin


# ───────────────────────────── Identifiants Home Assistant ─────────────────────────────

def slug(texte: str) -> str:
    """Équivalent de homeassistant.util.slugify (accents retirés, séparateur « _ »)."""
    logger.debug("slug() appelée")
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    identifiant = re.sub(r"[^a-z0-9]+", "_", texte.lower()).strip("_")
    logger.debug("slug() retourne | identifiant normalisé")
    return identifiant


def entite(domaine: str, appareil: str, nom: str) -> str:
    return f"{domaine}.{slug(appareil + ' ' + nom)}"


# ───────────────────────────── Vue « Voisins » ─────────────────────────────

def vue_voisins(voisins: list[dict], appareil: str) -> dict:
    logger.debug("vue_voisins() appelée | {} voisin(s)", len(voisins))
    if not voisins:
        logger.debug("vue_voisins() retourne | vue « aucun voisin »")
        return {
            "title": "Voisins", "path": "voisins", "icon": "mdi:account-group", "type": "sections",
            "sections": [{"type": "grid", "cards": [{
                "type": "markdown",
                "content": "Aucun voisin dans `secrets.yaml` (compteur1 … compteur10, voir README, « Voisins »).",
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
                {"type": "tile", "entity": entite("sensor", appareil, f"{nom} - Dernière trame"),
                 "name": "Dernière trame", "icon": "mdi:clock-check-outline", "vertical": True},
                {"type": "tile", "entity": entite("sensor", appareil, f"{nom} - Débit estimé"),
                 "name": "Débit estimé", "icon": "mdi:speedometer", "vertical": True},
                {
                    # Alertes du voisin (mêmes règles et seuils que ton compteur)
                    "type": "entities",
                    "title": "Alertes",
                    "show_header_toggle": False,
                    "state_color": True,
                    "entities": [
                        {"entity": entite("binary_sensor", appareil, f"{nom} - {alerte}"), "name": alerte}
                        for alerte in ("Fuite confirmée", "Fuite suspectée (nuit)", "Débit anormal",
                                       "Conso journalière anormale", "Compteur silencieux")
                    ],
                },
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
    vue = {
        "title": "Voisins", "path": "voisins", "icon": "mdi:account-group",
        "type": "sections", "max_columns": 3, "sections": sections,
    }
    logger.debug("vue_voisins() retourne | {} section(s)", len(sections))
    return vue


# ───────────────────────────── Jauges et actions ─────────────────────────────

def valeur_initiale(config: dict, ident: str) -> float | None:
    logger.debug("valeur_initiale() appelée | identifiant={}", ident)
    for n in config.get("number") or []:
        if isinstance(n, dict) and n.get("id") == ident and "initial_value" in n:
            logger.debug("valeur_initiale() retourne | valeur trouvée")
            return float(n["initial_value"])
    logger.debug("valeur_initiale() retourne | aucune valeur")
    return None


def regler_jauges(tableau: dict, appareil: str, seuil_debit: float, seuil_jour: float) -> None:
    """Max et paliers des jauges dérivés des seuils (mêmes proportions que les valeurs d'origine)."""
    logger.debug("regler_jauges() appelée | seuil débit={} seuil jour={}", seuil_debit, seuil_jour)
    regles = {
        entite("sensor", appareil, "Débit estimé"): (seuil_debit, 0.3, 1.5),
        entite("sensor", appareil, "Conso aujourd'hui"): (seuil_jour, 0.625, 1.25),
    }
    for carte in cartes(tableau):
        r = regles.get(carte.get("entity")) if carte.get("type") == "gauge" else None
        if not r:
            continue
        seuil, orange, maxi = r
        carte["max"] = round(seuil * maxi)
        carte["segments"] = [
            {"from": 0, "color": "#43a047"},
            {"from": round(seuil * orange), "color": "#fb8c00"},
            {"from": round(seuil), "color": "#e53935"},
        ]
    logger.debug("regler_jauges() retourne | jauges réglées")


def cartes(tableau: dict):
    logger.debug("cartes() appelée | parcours des cartes")
    for vue in tableau.get("views", []):
        for section in vue.get("sections", []):
            yield from section.get("cards", [])
    logger.debug("cartes() retourne | parcours terminé")


def paquet_ntfy(config: dict) -> bool:
    logger.debug("paquet_ntfy() appelée | recherche du paquet ntfy")
    for pkg in (config.get("packages") or {}).values():
        if isinstance(pkg, str) and "ntfy.yaml" in pkg:
            logger.debug("paquet_ntfy() retourne | True (paquet distant)")
            return True
        if isinstance(pkg, Include) and pkg.fichier.endswith("ntfy.yaml"):
            logger.debug("paquet_ntfy() retourne | True (paquet local)")
            return True
        if isinstance(pkg, dict) and any("ntfy.yaml" in str(f) for f in pkg.get("files") or []):
            logger.debug("paquet_ntfy() retourne | True (paquet fichiers)")
            return True
    logger.debug("paquet_ntfy() retourne | False")
    return False


def ajouter_actions_ntfy(tableau: dict, appareil: str) -> None:
    logger.debug("ajouter_actions_ntfy() appelée | appareil={}", appareil)
    for vue in tableau.get("views", []):
        for section in vue.get("sections", []):
            titres = [c.get("heading") for c in section.get("cards", []) if c.get("type") == "heading"]
            if "Actions" in titres:
                section["cards"].append({
                    "type": "entities",
                    "title": "Notifications ntfy",
                    "show_header_toggle": False,
                    "entities": [
                        {"entity": entite("switch", appareil, "ntfy - notifications actives"), "name": "Notifications actives"},
                        {"entity": entite("button", appareil, "ntfy - message de test"), "name": "Message de test"},
                        {"entity": entite("button", appareil, "ntfy - envoyer les bilans maintenant"), "name": "Envoyer les bilans maintenant"},
                    ],
                })
                logger.debug("ajouter_actions_ntfy() retourne | section Actions complétée")
                return
    logger.debug("ajouter_actions_ntfy() retourne | aucune section Actions trouvée")


# ───────────────────────────── Programme principal ─────────────────────────────

class Dumper(yaml.SafeDumper):
    """Listes indentées sous leur clé (même présentation que le fichier de base)."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def main() -> None:
    logger.debug("main() appelée | génération du tableau de bord")
    racine = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=racine / "compteur-eau-lora.yaml")
    ap.add_argument("--secrets", type=Path, help="défaut : secrets.yaml à côté de --config")
    ap.add_argument("--base", type=Path, default=racine / "ha_dashboard_compteur_eau.yaml")
    ap.add_argument("--sortie", type=Path, default=racine / "ha_dashboard_compteur_eau.genere.yaml")
    ap.add_argument("--appareil", help="nom de l'appareil dans HA (défaut : friendly_name de la configuration)")
    ap.add_argument("--seuil-debit", type=float, help="seuil de débit anormal en L/h (défaut : valeur de la configuration)")
    ap.add_argument("--seuil-jour", type=float, help="seuil de conso journalière en L (défaut : valeur de la configuration)")
    args = ap.parse_args()

    chemin_secrets = args.secrets or args.config.parent / "secrets.yaml"
    if not chemin_secrets.exists():
        logger.error("main() : {} introuvable (copie secrets.example.yaml en secrets.yaml)", chemin_secrets.name)
        sys.exit(f"{chemin_secrets} introuvable (copie secrets.example.yaml en secrets.yaml)")
    secrets = lire_yaml(chemin_secrets) or {}
    config = lire_yaml(args.config, secrets)

    esphome = config.get("esphome") or {}
    appareil = args.appareil or esphome.get("friendly_name") or esphome.get("name", "compteur-eau-lora")
    voisins = voisins_declares(config, secrets)

    tableau = lire_yaml(args.base)
    vues = [v for v in tableau.get("views", []) if v.get("path") != "voisins"]
    vues.append(vue_voisins(voisins, appareil))
    tableau["views"] = vues

    seuil_debit = args.seuil_debit or valeur_initiale(config, "seuil_debit_l_h") or 1000
    seuil_jour = args.seuil_jour or valeur_initiale(config, "seuil_jour_l") or 800
    regler_jauges(tableau, appareil, seuil_debit, seuil_jour)
    ntfy = paquet_ntfy(config)
    if ntfy:
        ajouter_actions_ntfy(tableau, appareil)

    entete = (
        "# Tableau de bord GÉNÉRÉ par scripts/generer_tableau_de_bord.py : ne pas modifier à la main,\n"
        "# relancer le script après avoir ajouté ou retiré un voisin.\n"
        f"# Appareil : {appareil} | voisins : {', '.join(v['nom'] for v in voisins) or 'aucun'}\n"
        f"# Jauges : seuil débit {seuil_debit:g} L/h, seuil jour {seuil_jour:g} L | ntfy : {'oui' if ntfy else 'non'}\n"
    )
    texte = yaml.dump(tableau, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=1000)
    args.sortie.write_text(entete + texte, encoding="utf-8")
    print(f"{args.sortie.name} : {len(voisins)} voisin(s) ({', '.join(v['nom'] for v in voisins) or 'aucun'})")
    logger.debug("main() retourne | tableau de bord écrit")


if __name__ == "__main__":
    main()
