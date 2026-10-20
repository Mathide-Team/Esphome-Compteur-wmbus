#!/usr/bin/env python3
"""CI : écrit une variante de compteur-eau-lora.yaml avec N voisins (0 à 10, numéros factices).

    python3 scripts/ci_voisins.py 10    # → ci-voisins-10.yaml + ci-secrets-10.yaml

Les voisins sont déduits de secrets.yaml (voisins/voisins.yaml) : le script écrit
ci-secrets-N.yaml (secrets.example.yaml sans ses voisins, plus N voisins de test) et une copie
de compteur-eau-lora.yaml qui fusionne ce fichier au lieu de secrets.yaml et inclut les modèles
locaux (ceux de la branche) au lieu du paquet GitHub. Avec N = 10, il teste
aussi les entrées facultatives : type_compteur izar, clés AES, typecompteurN, n° sans « 0x ».
Les fichiers produits ne sont pas versionnés (.gitignore).
"""

import re
import sys
from pathlib import Path

racine = Path(__file__).resolve().parent.parent
n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
if not 0 <= n <= 10:
    sys.exit("N doit être compris entre 0 et 10")

FUSION = "  <<: !include secrets.yaml\n"
source = (racine / "compteur-eau-lora.yaml").read_text(encoding="utf-8")
if FUSION not in source:
    sys.exit("compteur-eau-lora.yaml : ligne « <<: !include secrets.yaml » introuvable")
# Modèles chargés depuis GitHub (ref main) par défaut (issue #36) : la CI valide ceux de la
# branche testée, inclus localement à la place du paquet distant.
DISTANT = re.compile(r"^  voisins:\n    url: https://github\.com/Mathilde-Team/Esphome-Compteur-wmbus\n(?:    .*\n)+", re.M)
if not DISTANT.search(source):
    sys.exit("compteur-eau-lora.yaml : paquet « voisins » (url GitHub) introuvable")
source = DISTANT.sub("  voisins: !include voisins/voisins.yaml\n", source, count=1)
(racine / f"ci-voisins-{n}.yaml").write_text(
    source.replace(FUSION, f"  <<: !include ci-secrets-{n}.yaml\n", 1), encoding="utf-8"
)

secrets = (racine / "secrets.example.yaml").read_text(encoding="utf-8")
secrets = re.sub(r"^#?\s*(nom|cle|type)?compteur([1-9]|10):.*\n", "", secrets, flags=re.M)
lignes = [f'compteur{i}: "0x{0x10000000 + i:08X}"\nnomcompteur{i}: "Test {i}"\n' for i in range(1, n + 1)]
if n == 10:
    lignes[6] = 'compteur7: "10000007"\n'          # sans « 0x », nom par défaut
    lignes += [
        "type_compteur: izar\n",
        'typecompteur2: "dme_07"\n',
        'aes: "AABBCCDDEEFF00112233445566778899"\n',
        'aesv3: "00112233445566778899001122334455"\n',  # que des chiffres : reste une chaîne
        'aesv4: ""\n',                                  # vide = en clair
    ]
(racine / f"ci-secrets-{n}.yaml").write_text(secrets + "\n# ── CI ──\n" + "".join(lignes), encoding="utf-8")
print(f"ci-voisins-{n}.yaml + ci-secrets-{n}.yaml : {n} voisin(s)")
