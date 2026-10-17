# Compteur d'eau wM-Bus → ESPHome → Home Assistant

Lecture radio (wM-Bus, mode T1, 868,95 MHz) du compteur d'eau de la maison **et** de compteurs voisins, avec une carte ESP32-S3 équipée d'une radio SX1262 et d'un écran OLED. Les mesures remontent dans Home Assistant (HA) ; HA écrit un fichier CSV des relevés et pourra prévenir les voisins (MQTT, notification…).

## Ce que fait le projet

- **Ton compteur** : index, RSSI, statut, débit estimé, conso de la dernière heure / du jour / d'hier, détection de fuite et alertes.
- **Jusqu'à 4 compteurs voisins** : index, conso du jour et RSSI de chacun (pas d'alertes).
- **Écran OLED** (compteur de la maison) : 3 pages qui tournent toutes les 5 s.
- **Compteurs inconnus** : tous les compteurs captés par la radio, déclarés ou non, sont aussi envoyés à HA sous forme d'événement (numéro + RSSI).
- **Export CSV** : HA ajoute une ligne par compteur (au plus toutes les 5 min) à un fichier CSV. Un script Python extrait aussi un CSV à partir des logs ESPHome.

## Matériel

Carte avec ESP32-S3, radio SX1262 (TCXO, commutateur RF sur DIO2) et OLED SSD1306 128×64 intégrés. Le brochage utilisé est celui de la **Heltec WiFi LoRa 32 V3** :

| Fonction | Broche |
|---|---|
| SPI CLK / MOSI / MISO | GPIO9 / GPIO10 / GPIO11 |
| SX1262 CS / RESET / IRQ (DIO1) / BUSY | GPIO8 / GPIO12 / GPIO14 / GPIO13 |
| OLED SDA / SCL / RESET | GPIO17 / GPIO18 / GPIO21 |
| Vext (alimente l'OLED et l'étage RF, actif à l'état bas) | GPIO36 |

Logiciel : ESPHome (configuration validée avec **2026.9.1**), composant externe [`SzczepanLeon/esphome-components`](https://github.com/SzczepanLeon/esphome-components) (`wmbus_radio`, `wmbus_meter`, `wmbus_common`). Les compteurs lus sont des compteurs d'eau DME, driver `dme_07`.

## Fichiers du dépôt

| Fichier | Rôle |
|---|---|
| `compteur-eau-lora.yaml` | Configuration ESPHome complète (ton compteur + 4 voisins + écran) |
| `secrets.example.yaml` | Modèle du `secrets.yaml` (à copier et remplir, ne jamais publier le vrai) |
| `ha_automation_releves_csv.yaml` | Automatisation Home Assistant qui écrit le CSV |
| `wmbus_log_to_csv.py` | Extrait un CSV à partir d'un log ESPHome |

## Installation

### 1. Secrets

Copie `secrets.example.yaml` en `secrets.yaml` et remplis-le. Les numéros de compteur se mettent **entre guillemets, avec le préfixe `0x`**, avec les chiffres imprimés sur le compteur :

| Clé | Contenu |
|---|---|
| `compteur0` | numéro de **ton** compteur |
| `compteur1` … `compteur4` | numéros des compteurs voisins |
| `nomcompteur1` … `nomcompteur4` | noms affichés dans HA (ex. `"Dupont"`) |

Pour avoir moins de 4 voisins, supprime dans `compteur-eau-lora.yaml` les blocs « Voisin N » correspondants (substitutions, `wmbus_meter`, `globals`, `sensor`). Si un voisin a un autre modèle de compteur, change son `type` dans `wmbus_meter`.

### 2. Flasher

```bash
esphome config compteur-eau-lora.yaml   # vérifie la configuration
esphome run compteur-eau-lora.yaml      # compile et flashe
```

### 3. Home Assistant

L'appareil est découvert par l'intégration ESPHome. Pour le CSV, voir [Export CSV](#export-csv-dans-home-assistant).

## Entités Home Assistant

**Ton compteur**

| Entité | Description |
|---|---|
| Compteur eau - Volume total | Index en m³ |
| Compteur eau - RSSI / Statut | Qualité du signal radio, statut du compteur |
| WiFi RSSI | Signal WiFi de la carte |
| Débit estimé | L/h, calculé entre deux trames espacées d'au moins 120 s |
| Conso dernière heure | L, mise à jour toutes les heures pile |
| Conso aujourd'hui / Conso hier | L (voir plus bas) |
| Heures de conso continue | Nombre d'heures consécutives avec consommation |
| Fuite - conso min par heure, Fuite - heures consécutives, Seuil débit anormal, Seuil conso journalière | Seuils réglables depuis HA |
| Mode absence | Interrupteur |
| 6 capteurs « problème » | Voir [Alertes](#détection-de-fuite-et-alertes) |

**Chaque voisin** (nom = `nomcompteurN`) : `Nom - Index` (m³), `Nom - Conso aujourd'hui` (L), `Nom - RSSI` (diagnostic).

## Calcul de la conso du jour

```
conso du jour (L) = (index courant − 1er index du jour) × 1000
```

- Le **1er index du jour** est l'index de la première trame reçue dans la journée.
- La valeur par défaut est **0** : tant qu'aucun index n'est connu, par exemple juste après un redémarrage et avant la prochaine trame, la conso affichée est 0.
- Le jour de référence est mémorisé en flash : un redémarrage dans la journée ne perd pas le 1er index du jour.
- Limites : si l'ESP est éteint au début de la journée, le 1er index est celui de la première trame reçue après son retour. La consommation entre la dernière trame de la veille et la première du jour n'est comptée dans aucun des deux jours.
- « Conso hier » (ton compteur) est publiée à minuit : dernier index de la journée moins 1er index de la journée.

## Écran OLED

Il affiche le compteur de la maison, une page toutes les 5 s :

1. **Index** (police réduite à partir de 1000 m³), **conso du jour** et numéro du compteur.
2. **Signaux** WiFi et wM-Bus : barres (4 niveaux) et dBm. Seuils WiFi : -55 / -67 / -75 / -85 dBm. Seuils radio : -60 / -75 / -90 / -100 dBm.
3. **Alertes actives** (jusqu'à 4 lignes, puis « +N autres »). Cette page est sautée s'il n'y a aucune alerte.

## Détection de fuite et alertes

Uniquement pour le compteur de la maison.

| Alerte | Se déclenche quand |
|---|---|
| Fuite confirmée | La conso de chaque heure atteint au moins `Fuite - conso min par heure` (1 L par défaut) pendant au moins `Fuite - heures consécutives` heures (24 par défaut) |
| Fuite suspectée (nuit) | À 5 h, au moins 3 heures consécutives avec consommation |
| Débit anormal | Débit estimé supérieur à `Seuil débit anormal` (1000 L/h par défaut) pendant 10 min |
| Conso journalière anormale | Conso du jour supérieure à `Seuil conso journalière` (800 L par défaut) |
| Conso pendant absence | `Mode absence` activé et au moins 1 L consommé pendant l'heure écoulée |
| Compteur silencieux | Aucune trame reçue depuis plus de 6 h |

La résolution de l'index est de 1 L : le débit estimé est donc grossier pour les petits débits.

## Export CSV dans Home Assistant

**Principe** : l'ESP ne peut pas écrire de fichier dans HA. Il envoie donc à HA, pour **chaque compteur capté** (connu ou inconnu), un événement `esphome.wmbus_frame` contenant `compteur` (8 chiffres, sans `0x`) et `rssi` (dBm). Il en envoie au plus un toutes les `intervalle_csv_s` secondes (300 par défaut, substitution du YAML) par compteur. Une automatisation HA ajoute alors une ligne au CSV avec l'action `notify.send_message` de l'intégration **File**.

1. **Autoriser l'appareil** : Paramètres → Appareils et services → ESPHome → ton appareil → Configurer → autoriser l'appareil à effectuer des actions Home Assistant. Sans cela, HA ignore les événements.
2. **Autoriser le dossier** dans `configuration.yaml`, puis redémarrer HA :
   ```yaml
   homeassistant:
     allowlist_external_dirs:
       - /config/releves
   ```
3. **Créer le fichier** `/config/releves/releves_compteurs.csv` avec uniquement la ligne d'en-tête ci-dessous. Sur un fichier vide, l'intégration File ajoute sa propre ligne d'introduction ; avec l'en-tête déjà en place, le fichier reste un CSV propre :
   ```
   timestamp;compteur;statut;rssi_dbm;index_m3;conso_jour_l
   ```
4. **Ajouter l'intégration File** (Paramètres → Appareils et services → Ajouter une intégration → File), choisir la notification, chemin `/config/releves/releves_compteurs.csv`, horodatage désactivé (la ligne a déjà le sien). Note l'identifiant de l'entité `notify.…` créée.
5. **Ajouter l'automatisation** `ha_automation_releves_csv.yaml` après l'avoir adaptée : la table `compteurs` (numéros sans `0x` et identifiants des entités index / conso de chaque compteur connu) et l'entité `notify`.
6. **Vérifier** : Outils de développement → Événements → écouter `esphome.wmbus_frame`.

Ne place pas le fichier dans `/config/www` : son contenu serait accessible sans authentification à l'adresse `/local/`.

Exemple de fichier obtenu (numéros fictifs) :

```
timestamp;compteur;statut;rssi_dbm;index_m3;conso_jour_l
2026-10-17 00:42:17;12345678;connu;-40;337,693;12
2026-10-17 00:42:19;23456789;connu;-61;1204,512;85
2026-10-17 00:42:20;99999999;inconnu;-70;;
```

Pour les compteurs **inconnus** (non déclarés), seuls le numéro et le RSSI sont disponibles : leurs trames sont chiffrées et l'ESP ne les décode pas.

**Autre piste, sans configuration** : le panneau Historique de HA a un bouton « Télécharger les données » (export CSV des entités choisies). Il ne couvre que les compteurs déclarés, et le recorder ne garde par défaut que 10 jours de données détaillées.

### Extraire un CSV depuis les logs

```bash
python wmbus_log_to_csv.py mon.log -o releves.csv
esphome logs compteur-eau-lora.yaml | python wmbus_log_to_csv.py -o releves.csv
```

Une ligne par trame valide reçue, avec les mêmes colonnes que ci-dessus. Le statut est « connu » pour les compteurs déclarés dans la configuration ou décodés par l'ESP. Options : `--date`, `--sep` (défaut `;`), `--decimal` (défaut `,`), `--prefixe-propre`, `-a` pour ajouter à un CSV existant.

## Prévenir les voisins (extension)

L'automatisation sépare la construction de la ligne (`ligne`) de son envoi : il suffit d'ajouter une action après `notify.send_message`. Le fichier contient un bloc commenté prêt à l'emploi pour **MQTT** (un topic par compteur). On peut aussi utiliser `notify.mobile_app_…`, Telegram ou un e-mail. Chaque voisin ne doit recevoir que **son** compteur (un topic et des droits de broker par voisin).

## Dépannage

| Symptôme | Piste |
|---|---|
| Log : `Telegram not handled by any handler` | Trame d'un compteur non déclaré. Normal pour les compteurs des autres. Pour en lire un, ajoute son numéro dans `secrets.yaml` |
| Trames d'un compteur reçues mais index vide | Vérifier le `type` (driver) et la clé de chiffrement éventuelle (option `key` du composant `wmbus_meter`, voir sa documentation) |
| Écran noir au démarrage | Vext doit être allumé avant l'init de l'OLED : c'est le rôle de `on_boot` (priorité 799). Ne pas la modifier |
| Conso du jour à 0 | Normal avant la première trame de la journée ou juste après un redémarrage |
| HA ne reçoit pas les événements | Vérifier l'autorisation de l'appareil (étape 1 de l'export CSV) |
| Erreur de compilation sur un `meter_id` | Le numéro doit être entre guillemets avec `0x` dans `secrets.yaml` |

## Vie privée et limites

- Ne lis et ne partage que les compteurs dont le propriétaire est d'accord. Les numéros de compteur et les consommations sont des données personnelles.
- Ne publie jamais `secrets.yaml`, les logs ni les CSV contenant de vrais numéros. `.gitignore` proposé :
  ```
  secrets.yaml
  *.log
  releves*.csv
  .esphome/
  ```
- Portée radio : les compteurs lointains (RSSI inférieur à -90 dBm) sont reçus de façon irrégulière et leur index peut tarder à apparaître.

## Crédits

[ESPHome](https://esphome.io), [Home Assistant](https://www.home-assistant.io), [SzczepanLeon/esphome-components](https://github.com/SzczepanLeon/esphome-components) pour le décodage wM-Bus, [Material Design Icons](https://pictogrammers.com/library/mdi/) pour les pictogrammes de l'écran.
