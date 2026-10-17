# Export CSV des relevés dans Home Assistant

Tutoriel complet : chaque compteur capté par l'ESP (le tien, ceux des voisins déclarés et les **inconnus**) devient une ligne d'un fichier CSV, avec l'heure, le numéro, le RSSI, l'index et la conso du jour.

**Sans code Python, et sans modifier `configuration.yaml`** : tout se fait depuis l'interface de Home Assistant.

## Principe

ESPHome ne peut pas écrire dans le système de fichiers de Home Assistant (HA). Le travail est donc partagé :

```
compteur wM-Bus ──radio──> ESP32 ──évènement « esphome.wmbus_trame »──> HA ──automatisation──> notify (File) ──> CSV
                                                                          └──> (option) autre notify : MQTT, ntfy, téléphone…
```

1. **L'ESP** lit chaque trame radio, retrouve le numéro du compteur et envoie à HA un **évènement** `esphome.wmbus_trame`. Il en envoie au plus un par compteur et par intervalle, réglable avec le nombre « Export CSV - intervalle » (15 min par défaut). L'interrupteur « Export CSV actif » met l'export en pause.
2. **HA** reçoit l'évènement. Une **automatisation** met les valeurs en forme de ligne CSV et appelle `notify.send_message` sur l'entité de l'intégration **File**, qui **ajoute** la ligne à la fin du fichier, sans jamais l'écraser.
3. La même ligne peut partir **en plus** vers un autre `notify`, par exemple pour prévenir un voisin (voir [Prévenir les voisins](#prévenir-les-voisins)).

### Contenu de l'évènement

| Champ | Exemple | Compteur inconnu |
|---|---|---|
| `compteur` | `12345678` (8 chiffres, sans `0x`) | numéro lu dans l'en-tête de la trame |
| `nom` | `Mon compteur`, `Dupont` | vide |
| `statut` | `connu` | `inconnu` |
| `rssi_dbm` | `-61` | renseigné |
| `index_m3` | `337.693` | vide (trame chiffrée, non décodée) |
| `conso_jour_l` | `12` | vide |

**Conso du jour** (litres) = (index courant − 1er index du jour) × 1000. Le 1er index du jour est celui de la première trame reçue dans la journée ; la **valeur par défaut est 0**. C'est le même calcul que pour l'écran et l'entité « Conso aujourd'hui ».

## Étape 1 : autoriser l'ESP à envoyer des évènements

Paramètres → Appareils et services → **ESPHome** → `compteur-eau-lora` → **Configurer** → coche « **Autoriser l'appareil à effectuer des actions Home Assistant** » → Valider.

Sans cette case, HA ignore les évènements de l'ESP. Rien n'apparaît, et aucune erreur n'est affichée.

**Contrôle** : Outils de développement → **Évènements** → « Écouter les évènements » → `esphome.wmbus_trame` → **Commencer à écouter**. Des évènements doivent arriver au fil des trames, en quelques minutes.

## Étape 2 : choisir où écrire le fichier

Par sécurité, l'intégration File n'écrit que dans des dossiers autorisés. **Sans configuration**, HA autorise déjà le dossier `www` et les dossiers média ([documentation de Home Assistant Core](https://www.home-assistant.io/integrations/homeassistant/)) :

| Emplacement | `configuration.yaml` | Recommandé ? |
|---|---|---|
| **`/media/releves_compteurs.csv`** | rien à écrire | ✅ Oui. C'est le dossier média par défaut de Home Assistant OS, Supervised et Docker (avec HA Core installé dans un environnement Python, c'est `/config/media`). Accessible avec les modules Samba, Studio Code Server ou Terminal |
| `/config/www/releves_compteurs.csv` | rien à écrire | ❌ Non. Le contenu de `www` est **public**, sans authentification, à l'adresse `http://<ha>:8123/local/releves_compteurs.csv` : numéros et consommations des voisins y seraient exposés |
| `/config/releves/releves_compteurs.csv` | ajouter `allowlist_external_dirs` (ci-dessous) | ✅ Oui, si tu préfères garder le fichier avec la configuration (sauvegardé avec elle) |

Variante avec `configuration.yaml`, si tu le souhaites, puis redémarrage de HA :

```yaml
homeassistant:
  allowlist_external_dirs:
    - /config/releves
```

Le **dossier** doit exister. L'intégration crée le fichier, mais pas le dossier ([documentation de l'intégration File](https://www.home-assistant.io/integrations/file/)). `/media` existe déjà.

## Étape 3 (facultative) : l'en-tête du CSV

Quand l'intégration File crée elle-même le fichier, elle commence par quelques lignes d'introduction : « Home Assistant notifications (Log started: …) » et une ligne de séparation. Pour obtenir un CSV propre, crée le fichier **avant**, avec cette seule ligne, par exemple avec le module Samba ou Studio Code Server :

```
timestamp;compteur;nom;statut;rssi_dbm;index_m3;conso_jour_l
```

Sinon, laisse HA créer le fichier, et ignore les premières lignes à l'ouverture : LibreOffice propose « À partir de la ligne », et Excel « Démarrer l'importation à la ligne ».

## Étape 4 : ajouter l'intégration File (notification)

1. Paramètres → Appareils et services → **Ajouter une intégration** → **File**.
2. Choisis **Configurer un service de notification** (« Set up a notification service »).
3. **Chemin du fichier** : `/media/releves_compteurs.csv` (ou le chemin choisi à l'étape 2).
4. **Horodatage** : **décoché**. La ligne contient déjà le sien, au format local `AAAA-MM-JJ HH:MM:SS`.
5. Valider. Note le nom de l'entité créée, par exemple `notify.releves_compteurs` ; tu peux la renommer depuis ses paramètres.

**Test** : Outils de développement → **Actions** → `notify.send_message`, cible : l'entité File, message : `test`. La ligne `test` doit apparaître à la fin du fichier. Supprime-la ensuite.

## Étape 5 : créer l'automatisation (dans l'interface)

1. Paramètres → **Automatisations et scènes** → **Créer une automatisation** → **Créer une nouvelle automatisation**.
2. Menu **⋮** → **Modifier en YAML**.
3. Remplace tout le contenu par celui de [`ha_automation_releves_csv.yaml`](../ha_automation_releves_csv.yaml).
4. Adapte la seule ligne marquée `À ADAPTER` : `entity_id: notify.releves_compteurs`, avec l'entité de l'étape 4.
5. **Enregistrer**.

L'automatisation est ainsi stockée par HA lui-même : il n'y a rien à modifier dans `configuration.yaml` ni dans `automations.yaml`.

Ce qu'elle fait :
- **déclencheur** : l'évènement `esphome.wmbus_trame` ;
- **variables** : `d` reçoit les données de l'évènement, `ligne` les met en forme (séparateur `;`, décimale `,` pour l'index, pratique dans un tableur français) ;
- **action** : `notify.send_message` vers l'entité File ;
- **mode** `queued` (jusqu'à 50) : plusieurs compteurs entendus à la même seconde produisent bien une ligne chacun.

## Résultat

```
timestamp;compteur;nom;statut;rssi_dbm;index_m3;conso_jour_l
2026-10-17 08:15:02;12345678;Mon compteur;connu;-41;337,693;12
2026-10-17 08:15:04;23456789;Dupont;connu;-63;1204,512;85
2026-10-17 08:15:09;99999999;;inconnu;-88;;
```

Numéros fictifs. Pour un compteur **inconnu**, seuls le numéro et le RSSI sont connus : sa trame est chiffrée et l'ESP ne la décode pas. Pour obtenir son index, déclare-le comme voisin dans `secrets.yaml`, avec l'accord de son propriétaire.

Récupérer le fichier : module **Samba** (partage `media`), **Studio Code Server** (clic droit → Télécharger), ou `scp` avec le module SSH.

## Prévenir les voisins

L'automatisation construit d'abord la `ligne`, puis l'envoie. Pour la renvoyer ailleurs, il suffit d'ajouter une action après `notify.send_message`. Le fichier contient un bloc commenté prêt à l'emploi :

- **MQTT** : `mqtt.publish` sur `compteurs_eau/<numéro>/releve`, uniquement pour les compteurs connus. Il faut l'intégration MQTT et un broker où **chaque voisin n'a le droit de lire que son propre topic** (ACL Mosquitto).
- **Autres notify** : `notify.mobile_app_<téléphone>`, Telegram, e-mail, ou **ntfy** avec l'intégration ntfy de HA.
- **Sans HA** : l'ESP peut prévenir les voisins lui-même avec ntfy. Voir le dépôt [Esphome-Compteur-wmbus-ntfy](https://github.com/Mathide-Team/Esphome-Compteur-wmbus-ntfy).

Un voisin ne doit jamais recevoir le relevé d'un autre : un topic ou un sujet par personne.

## Variantes (pour mémoire)

| Variante | Quand | Limite |
|---|---|---|
| **Historique de HA** → « Télécharger les données » | Export ponctuel sans rien configurer | Compteurs déclarés seulement (pas d'inconnus) ; 10 jours de détail par défaut (`recorder`) |
| **Carte SD sur l'ESP** (`sd_mmc_card`, écriture en ajout) | Pas de HA | Nécessite un lecteur SD ; le fichier reste sur la carte |
| **Webhook HA** (`http_request.post` de l'ESP vers un déclencheur webhook) | Remplacer l'évènement natif | Plus de configuration, sans bénéfice ici : l'évènement ESPHome fait déjà le travail |

## Dépannage

| Symptôme | Cause probable |
|---|---|
| Aucun évènement dans Outils de développement → Évènements | Case « Autoriser l'appareil à effectuer des actions » non cochée (étape 1), ou interrupteur « Export CSV actif » éteint |
| Évènements reçus, mais fichier vide | Mauvaise entité dans l'automatisation, ou automatisation désactivée. Regarde sa **trace** (Automatisations → ⋮ → Traces) |
| Erreur « path is not allowed » ou fichier jamais créé | Chemin hors des dossiers autorisés (étape 2), ou dossier inexistant |
| Trop de lignes | Augmente « Export CSV - intervalle » (en minutes, par compteur) |
| `conso_jour_l` toujours à 0 | Normal avant la 2e trame de la journée et juste après minuit. Sinon, lis les journaux de l'ESP : la ligne `[conso] 1er index du jour` doit apparaître une fois par jour et par compteur, et `Heure non synchronisée` signale que l'ESP n'a pas encore l'heure de HA |
