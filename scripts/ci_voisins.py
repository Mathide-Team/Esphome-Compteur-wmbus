#!/usr/bin/env python3
"""CI : écrit une variante de compteur-eau-lora.yaml avec N voisins (0 à 10, numéros factices).

    python3 scripts/ci_voisins.py 10    # → ci-voisins-10.yaml, à valider avec « esphome config »

Les lignes « voisinX: !include { file: voisins/voisin.yaml … } » sont remplacées par N lignes
de test. Le fichier produit n'est pas versionné (.gitignore).
"""

import re
import sys
from pathlib import Path

racine = Path(__file__).resolve().parent.parent
n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
if not 0 <= n <= 10:
    sys.exit("N doit être compris entre 0 et 10")

ligne_voisin = re.compile(r"^\s+voisin\d+: !include \{ file: voisins/voisin\.yaml.*$\n", re.M)
source = (racine / "compteur-eau-lora.yaml").read_text(encoding="utf-8")
if not ligne_voisin.search(source):
    sys.exit("Aucune ligne voisin trouvée dans compteur-eau-lora.yaml")

lignes = "".join(
    f'  voisin{i}: !include {{ file: voisins/voisin.yaml, vars: {{ i: {i}, num: "0x{0x10000000 + i:08X}", nom: "Test {i}" }} }}\n'
    for i in range(1, n + 1)
)
premiere = ligne_voisin.search(source).start()
sortie = ligne_voisin.sub("", source)
sortie = sortie[:premiere] + lignes + sortie[premiere:]
if n == 0:
    sortie = sortie.replace("\npackages:\n", "\npackages: {}\n", 1)
(racine / f"ci-voisins-{n}.yaml").write_text(sortie, encoding="utf-8")
print(f"ci-voisins-{n}.yaml : {n} voisin(s)")
