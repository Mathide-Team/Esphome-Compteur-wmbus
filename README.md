# Compteur d'eau wM-Bus → ESPHome → Home Assistant

Lecture radio (wM-Bus, mode T1, 868,95 MHz) du compteur d'eau de la maison **et** de compteurs voisins, avec une carte ESP32-S3 équipée d'une radio SX1262 et d'un écran OLED. Les mesures remontent dans Home Assistant (HA) ; HA écrit un fichier CSV des relevés et pourra prévenir les voisins (MQTT, notification…).

## Ce que fait le projet

- **Ton compteur** : index, RSSI, statut, débit estimé, conso de la dernière heure / du jour / d'hier, détection de fuite et alertes.
- **Jusqu'à 4 compteurs voisins** : index, conso du jour et RSSI de chacun (pas d'alertes).
- **Écran OLED** (compteur de la maison) : 3 pages qui tournent toutes les 5 s.
- **Compteurs inconnus** : tous les compteurs captés par la radio, déclarés ou non, sont aussi envoyés à HA sous forme d'événement (numéro + RSSI).
- **Export CSV** : HA ajoute une ligne par compteur (au plus une par intervalle réglable, 15 min par défaut) à un fichier CSV, sans code Python ni modification de `configuration.yaml` ([tutoriel](docs/export-csv-home-assistant.md)).

## Matériel

Carte avec ESP32-S3, radio SX1262 (TCXO, commutateur RF sur DIO2) et OLED SSD1306 128×64 intégrés. Le brochage utilisé est celui de la **Heltec WiFi LoRa 32 V3** :

| Fonction | Broche |
|---|---|
| SPI CLK / MOSI / MISO | GPIO9 / GPIO10 / GPIO11 |
| SX1262 CS / RESET / IRQ (DIO1) / BUSY | GPIO8 / GPIO12 / GPIO14 / GPIO13 |
| OLED SDA / SCL / RESET | GPIO17 / GPIO18 / GPIO21 |
| Vext (alimente l'OLED et l'étage RF, actif à l'état bas) | GPIO36 |

Logiciel : ESPHome (configuration validée avec **2026.9.1**), composant externe [`SzczepanLeon/esphome-components`](https://github.com/SzczepanLeon/esphome-components) (`wmbus_radio`, `wmbus_meter`, `wmbus_common`). Les compteurs lus sont des compteurs d'eau DME, driver `dme_07`.

## Ma liste de courses

| Article | Rôle |
|---|---|
| [Heemol Carte de développement LoRa 32 V4 ESP32 avec écran OLED 0,96" (ESP32-S3R2, SX1262, WiFi, Bluetooth)](https://www.amazon.fr/dp/B0GCSS4YLL) | La carte : ESP32-S3 + radio SX1262 + écran OLED. C'est elle qui reçoit les trames wM-Bus des compteurs |
| [Coque pour LoRa ESP32 V3 avec antenne et batterie 3000 mAh tout-en-un, interface Type-C (version N35, noir)](https://www.amazon.fr/dp/B0FCC3K8KZ) | Boîtier de protection avec antenne et batterie intégrées |

La coque est vendue pour la V3 de la carte, mais elle est **100 % compatible avec la V4** : écran, connecteur USB-C et connecteur d'antenne tombent aux mêmes emplacements.

## Fichiers du dépôt

| Fichier | Rôle |
|---|---|
| `compteur-eau-lora.yaml` | Configuration ESPHome complète (ton compteur + écran + liste des voisins) |
| `voisins/voisin.yaml` | Modèle d'un compteur voisin, inclus une fois par voisin (0 à 10), voir [Voisins](#voisins--de-0-à-10) |
| `secrets.example.yaml` | Modèle du `secrets.yaml` (à copier et remplir, ne jamais publier le vrai) |
| `ha_automation_releves_csv.yaml` | Automatisation Home Assistant qui écrit le CSV (à coller dans l'éditeur d'automatisations) |
| `docs/export-csv-home-assistant.md` | Tutoriel de l'export CSV dans Home Assistant |
| `ha_dashboard_compteur_eau.yaml` | Tableau de bord Home Assistant « Compteur d'eau » (vue de base) |
| `scripts/generer_tableau_de_bord.py` | Génère le tableau de bord complet, avec une vue « Voisins » pour les voisins déclarés |
| `scripts/ci_voisins.py` | CI : variante de la configuration avec 0 à 10 voisins de test |
| `LICENSE` | Licence MIT |
| `.github/` | CI, garde `dev` → `main`, règles de protection versionnées |

## Installation

### 1. Secrets

Copie `secrets.example.yaml` en `secrets.yaml` et remplis-le. Les numéros de compteur se mettent **entre guillemets, avec le préfixe `0x`**, avec les chiffres imprimés sur le compteur :

| Clé | Contenu |
|---|---|
| `compteur0` | numéro de **ton** compteur |
| `type_compteur` | facultatif : `dme_07` (défaut, Grand Besançon), `izar` (Grand Belfort) ou `auto`, voir [Izar / DME](#izar--dme) |
| `aes` | facultatif : clé AES de ton compteur, seulement si l'opérateur chiffre (absente = en clair) |
| `compteur1` … `compteur10` | facultatifs : un **voisin existe dès que son `compteurN` est présent** |
| `nomcompteurN`, `aesvN`, `typecompteurN` | facultatifs : nom affiché dans HA, clé AES et type du voisin N |

Rien à modifier dans `compteur-eau-lora.yaml` pour les voisins : voir [Voisins](#voisins--de-0-à-10).

### 2. Premier flash (par USB)

Le tout premier firmware doit être installé par le câble USB. Les mises à jour suivantes passeront par le WiFi (OTA). Deux possibilités : compiler et flasher en une seule commande, ou flasher un `.factory.bin` déjà compilé.

#### 2.1 Donner à ton utilisateur l'accès au port série

Sous Linux, le module apparaît sous le nom `/dev/ttyACM0` (USB-JTAG intégré de l'ESP32-S3). Ce port appartient à `root:dialout` (`rw-rw----`). Si ton utilisateur n'est pas dans le groupe `dialout`, esptool comme le navigateur reçoivent « Permission denied ». **N'utilise pas sudo pour flasher et ne lance pas le navigateur en root** : donne plutôt les droits à ton utilisateur. Choisis une des deux méthodes ci-dessous.

Méthode 1 : groupe `dialout` (permanent, il faut se reconnecter)

```bash
sudo usermod -aG dialout $USER
# puis DÉCONNECTE-TOI de la session (ou redémarre) : fermer le terminal ne suffit pas
groups          # doit maintenant afficher « dialout »
```

Méthode 2 : règle udev (pas besoin de se reconnecter)

Avec cette règle, l'utilisateur connecté a accès aux puces Espressif (identifiant USB `303a`) :

```bash
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0660", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-esp32.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
# débranche puis rebranche le module, puis vérifie :
getfacl /dev/ttyACM0      # doit contenir « user:<ton_utilisateur>:rw- »
```

Accès d'une seule fois, perdu au débranchement : `sudo chmod 666 /dev/ttyACM0`.

#### 2.2 Option A : flasher depuis le navigateur (Edge ou Chrome)

Web Serial n'existe que dans Chrome, Edge et les autres navigateurs Chromium. Firefox et Safari ne l'ont pas. Le navigateur a **les mêmes droits que ton utilisateur** : il faut donc avoir fait l'étape 2.1 avant.

1. **Ferme complètement Edge**, car il continue souvent de tourner en arrière-plan avec ses anciens droits :
   ```bash
   pkill -f msedge        # pour Chrome : pkill -f chrome
   ```
   Relance-le ensuite normalement, **sans sudo**.
2. **Edge installé en Flatpak** (`flatpak run com.microsoft.Edge`) : la sandbox Flatpak cache les ports série. Autorise-les une fois pour toutes :
   ```bash
   flatpak override --user --device=all com.microsoft.Edge
   ```
   La version `.deb` ou `.rpm` de Microsoft n'a pas besoin de ce réglage.
3. Ouvre **https://web.esphome.io**. Web Serial n'accepte que le HTTPS ou `localhost`. Sur une page en `http://<ip>`, le bouton USB ne fait rien.
4. **Connect** → choisis le port (« USB JTAG/serial debug unit », ttyACM0).
5. **Install** → sélectionne `compteur-eau-lora-firmware.factory.bin` → attends la fin du flash.
6. Appuie sur **RST** pour redémarrer le module.

#### 2.3 Option B : flasher en ligne de commande (esptool)

```bash
python3 -m venv ~/esp
~/esp/bin/pip install esptool
~/esp/bin/esptool --chip esp32s3 --port /dev/ttyACM0 write-flash 0x0 compteur-eau-lora-firmware.factory.bin
```

- Le **`.factory.bin`** est une image complète (bootloader, table des partitions, application). Il se flashe à l'adresse **`0x0`**. Le `.ota.bin` ne sert qu'aux mises à jour OTA.
- `write-flash` est la syntaxe d'esptool v5. Les versions plus anciennes utilisent `write_flash`.
- N'installe pas le venv dans `/tmp` : ce dossier est vidé au redémarrage.

Compiler **et** flasher en une seule commande (ESPHome installé localement, `secrets.yaml` présent) :

```bash
~/esp/bin/pip install esphome
~/esp/bin/esphome config compteur-eau-lora.yaml                          # vérifie la configuration
~/esp/bin/esphome run compteur-eau-lora.yaml --device /dev/ttyACM0       # compile, flashe et affiche les logs
~/esp/bin/esphome logs compteur-eau-lora.yaml --device /dev/ttyACM0      # logs seuls
```

#### 2.4 Si le module n'est pas reconnu ou si le flash échoue

| Symptôme | Solution |
|---|---|
| `Permission denied` sur `/dev/ttyACM0` | Étape 2.1 (groupe `dialout` ou règle udev), puis relancer le navigateur ou le terminal |
| Le port n'apparaît pas dans Edge | Edge pas complètement fermé (`pkill -f msedge`), Edge en Flatpak sans `--device=all`, ou page en HTTP |
| `Failed to connect` / `No serial data received` | Mode bootloader : **maintiens BOOT (PRG), appuie sur RST, relâche BOOT**, puis recommence |
| `port is busy` / déconnexions aléatoires | ModemManager prend le port : `sudo systemctl stop ModemManager` |
| Aucun `/dev/ttyACM*` (`ls /dev/ttyACM*` vide) | Câble de charge seule (sans fils de données) : change de câble. `dmesg -w` doit afficher le module au branchement |

#### 2.5 Pourquoi l'installation depuis ESPHome Builder échoue

- Le Builder qui tourne **dans Home Assistant ou sur un serveur** ne voit que les ports USB **de ce serveur**, pas ceux de ton PC. Passe par **Install → Manual download → Factory format**, puis flashe avec l'option A ou B.
- L'option « Plug into this computer » du Builder utilise Web Serial : elle ne marche qu'en HTTPS. Sur un Builder ouvert en `http://<ip>:6052`, elle échoue.
- Une fois ce premier firmware installé et le module connecté au WiFi, **Install → Wirelessly** fait les mises à jour OTA (mot de passe `ota_password`).

### 3. Home Assistant

L'appareil est découvert par l'intégration ESPHome. Ensuite :
- [Tableau de bord Énergie](#tableau-de-bord-énergie-eau) : ajouter l'index comme source d'eau ;
- [Tableau de bord « Compteur d'eau »](#tableau-de-bord--compteur-deau-) : vue dédiée (jauges, alertes, historique, réglages) ;
- [Export CSV](#export-csv-dans-home-assistant) : fichier des relevés.

## La configuration ESPHome expliquée

Cette section suit `compteur-eau-lora.yaml` bloc par bloc, dans l'ordre du fichier.

### `substitutions` : les variables du fichier

```yaml
num_compteur: !secret compteur0
nom_moi: "Mon compteur"
mdi_url: "https://github.com/Templarian/MaterialDesign-Webfont/raw/v7.4.47/..."
```

- `${num_compteur}` : numéro de ton compteur, lu dans `secrets.yaml`. ESPHome le remplace partout dans le fichier : `meter_id` de `wmbus_meter`, reconnaissance de ton compteur dans `on_frame`, numéro affiché à l'écran.
- `fuseau`, `bouton_pin` : fuseau de l'heure Internet et broche du bouton de la carte.
- Les voisins ne sont plus des substitutions : ils sont déclarés dans `packages:` (voir [Voisins](#voisins--de-0-à-10)).
- `nom_moi` : nom donné à ton propre compteur dans l'événement CSV.
- `mdi_url` : police d'icônes Material Design, **figée en version 7.4.47** pour que les codes des icônes (`\U000F058C`…) ne changent pas lors d'une mise à jour.

### `esphome` : nom de l'appareil et allumage de l'écran

```yaml
on_boot:
  priority: 799
  then:
    - output.turn_on: vext_enable
    - lambda: delay(50);
```

- `name: compteur-eau-lora` : nom réseau (`compteur-eau-lora.local`) et préfixe des entités HA (`sensor.compteur_eau_lora_…`).
- `project` (`mathilde-team.compteur-eau-wmbus`, version `1.0.0`) : Home Assistant affiche l'appareil avec le fabricant **mathilde-team** et le modèle **compteur-eau-wmbus**, et la version `1.0.0 (ESPHome …)`. C'est le marqueur stable lu par les intégrations, voir [Marqueur stable pour les intégrations](#marqueur-stable-pour-les-intégrations) : ne pas le renommer.
- `on_boot` à la **priorité 799** : sur cette carte, l'OLED est alimenté par la sortie **Vext**. Celle-ci doit être allumée **après** l'initialisation des sorties GPIO (priorité 800, qui la remet à l'arrêt) et **avant** l'initialisation de l'écran (priorité 400). À 800, l'écran restait noir. Les 50 ms laissent l'alimentation se stabiliser.

### `esp32` : la puce

- `board: esp32-s3-devkitc-1`, `variant: esp32s3`, `flash_size: 16MB` : ESP32-S3 avec 16 Mo de flash.
- `framework: esp-idf` : framework Espressif, celui que demande le composant wM-Bus.

### `logger` : les journaux

- `level: DEBUG` : affiche chaque trame radio reçue (RSSI + contenu en hexadécimal) et la ligne `[csv]` de chaque compteur entendu.
- `hardware_uart: USB_SERIAL_JTAG` : les logs sortent par le port USB natif (`/dev/ttyACM0`), le même que celui du flash.

### `api`, `ota`, `wifi`, `captive_portal` : réseau et Home Assistant

- `api:` : connexion native avec Home Assistant (découverte automatique, entités, événements).
- `ota` : mises à jour par le WiFi, protégées par `ota_password`.
- `wifi` + `ap` : connexion à ta box. Si elle échoue, le module crée son propre point d'accès (`fallback_hotspot_ssid`).
- `captive_portal` : sur ce point d'accès de secours, une page web permet de saisir un autre WiFi.

### `time` : l'heure (HA ou Internet) et les tâches planifiées

Deux sources règlent la **même horloge** de l'ESP : Home Assistant (`platform: homeassistant`, id `ha_time`) et l'heure Internet (`platform: sntp`, fuseau `${fuseau}`, `Europe/Paris` par défaut). Dès que l'une des deux a répondu, `id(ha_time).now()` est valide. **Si HA est arrêté**, la conso du jour, la bascule de minuit et l'extinction nocturne de l'écran continuent avec l'heure Internet (il faut seulement le WiFi).

Le SNTP n'a pas d'`id` : si le paquet ntfy déclare aussi une source SNTP, ESPHome fusionne les deux en une seule. Il faut pour cela une version du paquet ntfy dont la source SNTP n'a pas d'`id` non plus (voir [Esphome-Compteur-wmbus-ntfy](https://github.com/Mathilde-Team/Esphome-Compteur-wmbus-ntfy)).

Deux tâches tournent à heure fixe :

**Chaque heure pile** (`minutes: 0, seconds: 0`) :
1. Conso de l'heure = (index actuel − index au début de l'heure) × 1000 → capteur « Conso dernière heure ».
2. Si cette conso atteint au moins le seuil `Fuite - conso min par heure`, le compteur d'heures consécutives `g_leak_hours` augmente de 1. Sinon, il revient à 0 et le drapeau de fuite de nuit est effacé.
3. À **5 h**, si au moins 3 heures de conso d'affilée sont comptées, `g_night_flag` passe à vrai (alerte « Fuite suspectée (nuit) »).

**Chaque jour à minuit** :
1. « Conso hier » = dernier index reçu − 1er index de la veille. Le jour de la veille est calculé à partir de minuit moins 1 h.
2. Les capteurs « Conso aujourd'hui » (toi et chaque voisin, qui ajoute sa propre tâche de minuit) sont recalculés et retombent à 0 jusqu'à la première trame du nouveau jour.

### `globals` : la mémoire interne

| Variable | Rôle | Gardée au redémarrage |
|---|---|---|
| `g_total` | Dernier index reçu de ton compteur (m³) | non |
| `g_rx_ts` | Heure de la dernière trame (alerte « compteur silencieux ») | non |
| `g_flow_total`, `g_flow_ts` | Point de référence du calcul de débit | non |
| `g_hour_start` | Index au début de l'heure courante | oui |
| `g_day_start`, `g_day` | 1er index du jour et jour de l'année correspondant | oui |
| `g_leak_hours`, `g_night_flag` | Heures de conso consécutives, drapeau de fuite de nuit | oui |
| `g_page` | Page affichée sur l'OLED (0, 1 ou 2) | non |
| `g_ecran_eteint`, `g_reveil_ms`, `g_pause_ms` | Écran éteint la nuit, réveil par le bouton (60 s), pause de la rotation après un appui (30 s) | non |
| `g_week_start`, `g_week`, `g_month_start`, `g_month` | 1er index de la semaine (lundi) et du mois, et période correspondante | oui |
| `vN_total`, `vN_day_start`, `vN_day` | Pareil pour chaque voisin N (index, 1er index du jour, jour), créées par `voisins/voisin.yaml` | oui (sauf `vN_total`) |
| `g_voisins`, `g_v_infos` | Tables remplies au démarrage par chaque voisin : numéro de compteur → voisin N, et voisin N → nom, index, conso du jour (export CSV) | non |
| `g_id_off` | Position du numéro de compteur dans l'en-tête des trames (4 ou 6), apprise automatiquement | oui |
| `g_csv_last` | Pour chaque numéro de compteur, l'instant du dernier événement CSV envoyé | non |
| `g_ev_nom`, `g_ev_index`, `g_ev_conso` | Valeurs préparées pour l'événement envoyé à HA | non |

`restore_value: yes` enregistre la valeur en flash : un redémarrage dans la journée ne fait pas perdre le 1er index du jour.

### `output` : la sortie Vext

`GPIO36` avec `inverted: true` : Vext est **actif à l'état bas**. `turn_on` met donc la broche à 0 V, ce qui alimente l'OLED et l'étage RF.

### `external_components` : le composant wM-Bus

`SzczepanLeon/esphome-components@main` fournit `wmbus_radio` (pilote de la radio SX1262), `wmbus_meter` (déclaration des compteurs) et `wmbus_common` (décodage, drivers comme `dme_07`). La branche `main` peut évoluer : en cas de souci après une mise à jour, fige une version (`@<tag>` ou `@<commit>`).

**Drivers disponibles** (vérifiés dans le code du composant, dossier `components/wmbus_common/`) : les drivers sont dérivés du code de [wmbusmeters](https://github.com/wmbusmeters/wmbusmeters) (mêmes noms, en-têtes GPL) — plus d'une centaine de familles (Diehl `dme_07`, `izar`, `hydrus`, `sharky`, `sharky774`, mais aussi apator, iperl, itron, amiplus… selon le type de compteur). La liste exacte est celle du composant, version figée par `@<tag>`/`@<commit>`. Le driver `auto` est un driver **générique** de détection (il n'est pas spécifique à Diehl) : un compteur de type non prévu peut être lu avec `type: auto`. Le Sharky 775 n'a pas de driver nommé : d'après les règles de détection du code, `sharky` détecte DME (fabricant) version `0x40` et `sharky774` les versions `0x41` — selon la version annoncée par le compteur ; en cas de doute, `auto` (#35).

### `spi` et `i2c` : les bus

- `spi` (CLK 9, MOSI 10, MISO 11) : liaison avec la radio SX1262.
- `i2c` (SDA 17, SCL 18, **400 kHz** pour un affichage plus rapide) : liaison avec l'OLED. `scan: false`, car le scan aurait lieu avant l'allumage de Vext et ne trouverait rien.

### `wmbus_radio` : la radio et le traitement de chaque trame

```yaml
radio_type: SX1262
cs_pin: GPIO8   reset_pin: GPIO12   irq_pin: GPIO14   busy_pin: GPIO13
rx_gain: BOOSTED   rf_switch: true   has_tcxo: true
```

- `rx_gain: BOOSTED` : sensibilité maximale du SX1262, pour capter aussi les compteurs voisins.
- `rf_switch: true` : le commutateur d'antenne est piloté par DIO2 de la radio.
- `has_tcxo: true` : la radio utilise un oscillateur compensé en température (TCXO), indispensable pour rester calée sur 868,95 MHz.

`on_frame` s'exécute **pour chaque trame reçue**, quel que soit le compteur :

1. **Log** : RSSI + trame complète en hexadécimal.
2. **Lambda « export CSV »** (ignorée si l'interrupteur « Export CSV actif » est coupé) :
   1. **Lecture de l'en-tête** : les 10 premiers octets sont convertis depuis l'hexadécimal. Une trame wM-Bus commence par L (longueur), C (contrôle), M M (fabricant), puis l'adresse, dont le numéro de compteur sur 4 octets.
   2. **Deux positions possibles** pour le numéro (octets 4 à 7 ou 6 à 9, petit-boutiste) selon le format de la trame. Les deux sont calculées (`id_a`, `id_b`).
   3. **Compteur connu ?** Les deux candidats sont comparés aux 5 numéros déclarés. Si l'un correspond, sa position est mémorisée dans `g_id_off` et servira ensuite pour lire le numéro des compteurs **inconnus**. Le numéro est donc appris automatiquement dès que ton compteur ou un voisin est entendu.
   4. **Anti-répétition** : un compteur ne génère au plus qu'un événement par intervalle (« Export CSV - intervalle », 15 min par défaut). La table `g_csv_last` est vidée au-delà de 64 compteurs différents, pour protéger la mémoire.
   5. **Envoi** : log `[csv] Compteur XXXXXXXX (connu/inconnu) RSSI …`, puis lancement du script `envoi_trame`.

### `wmbus_meter` : les compteurs déclarés

```yaml
- id: mon_compteur
  meter_id: ${num_compteur}
  type: dme_07
  mode: [T1]
```

- Un bloc pour toi ; chaque voisin ajoute le sien (`compteur_vN`) depuis `voisins/voisin.yaml`. `type: dme_07` est le driver des compteurs d'eau DME. Pour un voisin d'un autre modèle, ajoute `type:` dans ses `vars`.
- `mode: [T1]` : mode wM-Bus T1 (émission seule du compteur, 868,95 MHz), celui des compteurs d'eau.
- `meter_id` doit être un numéro précis (pas de joker) : **seuls les compteurs déclarés ici voient leur index décodé**. Les autres ne remontent que leur numéro et leur RSSI.
- Si un compteur a une trame chiffrée, ajoute sa clé avec l'option `key:` (voir la documentation du composant).

### `script` `envoi_trame` : l'événement envoyé à Home Assistant

Paramètres : `p_id` (numéro sur 8 chiffres hexadécimaux), `p_rssi` (dBm), `p_slot` (−1 = inconnu, 0 = toi, 1 à 10 = voisins). `mode: parallel` : plusieurs compteurs peuvent être traités en même temps.

1. **Attente de 2 s**, le temps que `wmbus_meter` décode la trame et mette l'index à jour.
2. Préparation du nom, de l'index (3 décimales) et de la conso du jour (litres) selon `p_slot`. Pour un compteur inconnu, index et conso restent vides.
3. Envoi de l'événement **`esphome.wmbus_trame`** :

| Champ | Contenu |
|---|---|
| `compteur` | Numéro du compteur, 8 chiffres hexadécimaux sans `0x` |
| `nom` | `nom_moi`, `nomcompteurN` ou vide (inconnu) |
| `statut` | `connu` ou `inconnu` |
| `rssi_dbm` | RSSI de la trame (dBm) |
| `index_m3` | Index en m³ (vide si inconnu) |
| `conso_jour_l` | Conso du jour en litres (vide si inconnu) |

### `sensor` : les capteurs

**Ton compteur**
- `Compteur eau - Volume total` (`total_m3`) : l'index. À chaque nouvelle valeur (`on_value`) :
  - mémorise l'index et l'heure de réception ;
  - fixe le **1er index du jour** si c'est la première trame de la journée, ou si l'index a reculé (compteur remplacé) ;
  - calcule le **débit** entre deux trames séparées d'au moins **120 s**. En dessous, la résolution de 1 L donne un débit trop imprécis.
- `Compteur eau - RSSI` : force du signal du compteur.
- Unités écrites en dur (`m³` sur les index, `dBm` sur les RSSI) : le composant publie `m3` et `dbm`, refusés ou mal reconnus par HA. Voir [Tableau de bord Énergie](#tableau-de-bord-énergie-eau).
- `WiFi RSSI` : force du signal WiFi, toutes les 30 s.
- Capteurs `template` : `Débit estimé` (L/h, `device_class: volume_flow_rate`), `Conso dernière heure`, `Conso hier`, `Heures de conso continue`, `Conso aujourd'hui` (recalculée toutes les 60 s, 0 par défaut).

**Chaque voisin** (créés par `voisins/voisin.yaml`) : `Nom - Index` (avec la même logique de 1er index du jour), `Nom - RSSI` et `Nom - Conso aujourd'hui`.

### `text_sensor`

`Compteur eau - Statut` : état renvoyé par le compteur (alarmes internes, par exemple fuite ou retour d'eau, selon le driver).

### `number` : les réglages modifiables depuis HA

| Entité | Défaut | Plage | Rôle |
|---|---|---|---|
| Fuite - conso min par heure | 1 L | 1 à 50 | Conso horaire à partir de laquelle une heure compte comme « avec conso » |
| Fuite - heures consécutives | 24 h | 3 à 72 | Durée avant l'alerte « Fuite confirmée » |
| Seuil débit anormal | 1000 L/h | 100 à 5000 | Seuil de l'alerte « Débit anormal » |
| Seuil conso journalière | 800 L | 100 à 5000 | Seuil de l'alerte « Conso journalière anormale » |
| Export CSV - intervalle | 15 min | 1 à 1440 | Au plus un événement CSV par compteur pendant cette durée |

`optimistic` + `restore_value` : la valeur choisie dans HA est appliquée tout de suite et gardée après un redémarrage.

### `switch` : les interrupteurs

- `Mode absence` (coupé par défaut) : active l'alerte « Conso pendant absence ».
- `Export CSV actif` (allumé par défaut) : coupé, plus aucun événement CSV n'est envoyé.

### `binary_sensor` : les 6 alertes

| Alerte | Condition dans le YAML |
|---|---|
| Fuite confirmée | `g_leak_hours` ≥ `Fuite - heures consécutives` |
| Fuite suspectée (nuit) | `g_night_flag` (fixé à 5 h, voir `time`) |
| Débit anormal | `Débit estimé` > `Seuil débit anormal` pendant **10 min** (`delayed_on`) |
| Conso journalière anormale | `Conso aujourd'hui` > `Seuil conso journalière` |
| Conso pendant absence | `Mode absence` allumé et `Conso dernière heure` ≥ 1 L |
| Compteur silencieux | Aucune trame depuis plus de **6 h** |

`device_class: problem` : HA les affiche comme « Problème / OK », ce qui facilite les automatisations de notification.

### `font` : les polices de l'écran

- Roboto en 4 tailles : `f_big` 22 px (index), `f_mid` 18 px (conso, dBm), `f_hdr` 14 px (titre des alertes), `f_small` 12 px (unités, numéro, libellés).
- `glyphs` : seuls les caractères listés sont compilés, ce qui économise la flash. Ils sont définis une fois (ancre YAML `&glyphes_texte`) et réutilisés (`*glyphes_texte`). Pour afficher un caractère absent (par exemple `ë`), ajoute-le à cette liste.
- Icônes Material Design en 3 tailles (26, 18, 14 px), avec uniquement les icônes utilisées.

### `interval` : la rotation des pages

Toutes les **5 s**, passage à la page suivante (0 → 1 → 2 → 0). La page 2 (alertes) est **sautée s'il n'y a aucune alerte active**.

### `display` : l'écran OLED

SSD1306 128×64 en I2C à l'adresse `0x3C`, reset sur GPIO21, redessiné toutes les 2 s.

- **Page 0 : index.** Goutte + index en m³ (police réduite à partir de 1000 m³, pour que 4 chiffres avant la virgule tiennent sur la ligne), conso du jour en litres, numéro du compteur sans le `0x` (`"${num_compteur}" + 2` saute les 2 premiers caractères).
- **Page 1 : signaux.** WiFi et radio wM-Bus, chacun avec 4 barres et la valeur en dBm. Seuils WiFi : −55 / −67 / −75 / −85 dBm. Seuils radio : −60 / −75 / −90 / −100 dBm. Ils se règlent dans les fonctions `niv_wifi` et `niv_rf`.
- **Page 2 : alertes.** Titre « ALERTE » + nombre d'alertes, puis jusqu'à 4 lignes (icône + libellé). S'il y en a plus de 4 : 3 lignes + « +N autres ».

### Adapter la configuration

**Nombre de voisins** : voir [Voisins](#voisins--de-0-à-10).

**Autre carte** : adapte les broches de `spi`, `wmbus_radio`, `i2c`, `display` et `output` (Vext). Si la carte n'a pas de Vext, supprime `output` et `on_boot`.

## Voisins : de 0 à 10

Les voisins sont **déduits de `secrets.yaml`** : rien à écrire dans `compteur-eau-lora.yaml`. Un voisin N (1 à 10) existe dès que `compteurN` y est présent et non vide :

```yaml
compteur1: "0x23456789"      # obligatoire pour que le voisin existe
nomcompteur1: "Dupont"       # facultatif : « Voisin 1 » par défaut
# aesv1: "…32 hex…"          # facultatif : clé AES de son compteur (absente ou "" = en clair)
# typecompteur1: "izar"      # facultatif : s'il diffère de type_compteur
```

| Entrée | Rôle |
|---|---|
| `compteurN` | Numéro du compteur, avec `0x` (ex. `"0x23456789"`), N de 1 à 10. **Garde le même N pour un voisin** : il fixe ses identifiants internes (`v1_total`, `compteur_v1`…) et donc son historique |
| `nomcompteurN` | Nom affiché dans HA : « Dupont - Index », « Dupont - RSSI », « Dupont - Conso aujourd'hui »… |
| `aesvN` | Clé AES-128 de son compteur, si l'opérateur chiffre les trames (voir [Izar / DME](#izar--dme)) |
| `typecompteurN` | Pilote de son compteur, si différent de `type_compteur` |

- **Ajouter un voisin** : ajoute `compteurN` (et `nomcompteurN`) dans `secrets.yaml`, puis recompile et installe (OTA).
- **Retirer un voisin** : supprime ou commente `compteurN`, ou mets-le à `""`. Dans HA, ses entités passent « indisponibles » : supprime-les depuis la page de l'appareil.
- **Aucun voisin** : aucun `compteurN`.
- Les emplacements peuvent avoir des trous (voisins 1, 2 et 5 par exemple).

Comment ça marche : `compteur-eau-lora.yaml` fusionne `secrets.yaml` dans ses `substitutions` (`<<: !include secrets.yaml`). [`voisins/voisins.yaml`](voisins/voisins.yaml) prévoit alors 10 emplacements, et chacun n'inclut le modèle [`voisins/voisin.yaml`](voisins/voisin.yaml) que si son `compteurN` existe. Ce sont les paquets conditionnels d'ESPHome (expressions Jinja, ESPHome ≥ 2025.x). Les valeurs restent masquées dans « Validate » et `esphome config`, comme avec `!secret`.

> **Mise à jour depuis la version avec une ligne par voisin** : remplace les lignes `voisinN: !include …` par le paquet `voisins:` de `compteur-eau-lora.yaml` (modèles chargés depuis GitHub, ou `voisins: !include voisins/voisins.yaml` hors ligne, voir ci-dessous). Ton `secrets.yaml` ne change pas : `compteur1`… `compteur4` et `nomcompteur1`… `nomcompteur4` y sont déjà, avec les mêmes N. L'historique est donc conservé. La déclaration à la main reste possible, **à la place** de `voisins/voisins.yaml` (pas en plus) : `voisin1: !include { file: voisins/voisin.yaml, vars: { i: 1, num: !secret compteur1, nom: !secret nomcompteur1 } }`.

> Paquet ntfy : chaque voisin y reçoit son bilan et les alertes de son compteur sur son sujet `ntfy_topic_vN`, également déduit de `secrets.yaml`. Voir [Esphome-Compteur-wmbus-ntfy](https://github.com/Mathilde-Team/Esphome-Compteur-wmbus-ntfy).

### Dans ESPHome Builder

ESPHome Builder (module complémentaire de Home Assistant, ou tableau de bord ESPHome) range ses fichiers dans le dossier `esphome` de la configuration HA (`/config/esphome/`). Son éditeur ne modifie que les fichiers d'appareils et ne sait pas créer de dossier. Les voisins se gèrent **uniquement dans les secrets** (bouton **Secrets** en haut à droite du Builder). Les modèles des dossiers `voisins/` et `options/` sont fournis de l'une des deux façons suivantes.

**Option A (par défaut) : modèles chargés depuis GitHub, aucun fichier à copier**

C'est ce que fait déjà `compteur-eau-lora.yaml` (issue #36) : ces fichiers ne contiennent aucun secret, ESPHome les télécharge.

```yaml
packages:
  voisins:
    url: https://github.com/Mathilde-Team/Esphome-Compteur-wmbus
    ref: main            # ou un tag de version, pour figer les modèles
    refresh: 1d
    files: [voisins/voisins.yaml]
```

Ce seul paquet suffit : il apporte aussi `voisin.yaml`, `cle.yaml` et `options/izar.yaml`, pris dans le même dépôt (testé). Les secrets restent dans ton `secrets.yaml`. Il faut un accès Internet à la compilation ; `refresh: 1d` limite le téléchargement à une fois par jour.

Dans le Builder : **Secrets** pour les voisins, puis `compteur-eau-lora` → **Validate** et **Install → Wirelessly**.

**Option B : copier les fichiers (hors ligne, ou modèles modifiés)**

Dans `compteur-eau-lora.yaml`, remplace le bloc `voisins:` (url, ref, refresh, files) de `packages:` par la ligne :

```yaml
packages:
  voisins: !include voisins/voisins.yaml
```

Puis fournis les fichiers :

1. Installe un module d'accès aux fichiers : **File editor** ou **Studio Code Server** (Paramètres → Modules complémentaires → Boutique), ou le partage réseau **Samba share**.
2. Dans le dossier `esphome`, crée les dossiers **`voisins`** et **`options`**, puis copie [voisins/voisins.yaml](voisins/voisins.yaml), [voisins/voisin.yaml](voisins/voisin.yaml), [voisins/cle.yaml](voisins/cle.yaml) et [options/izar.yaml](options/izar.yaml).
3. Vérifie l'arborescence :
   ```
   esphome/
   ├── compteur-eau-lora.yaml
   ├── secrets.yaml
   ├── options/
   │   └── izar.yaml
   └── voisins/
       ├── cle.yaml
       ├── voisin.yaml
       └── voisins.yaml
   ```
   Le Builder n'affiche que les fichiers à la racine de `esphome/` : les modèles, rangés dans des sous-dossiers, n'apparaissent pas comme de faux appareils.
4. Dans le Builder : **Secrets** pour les voisins, puis `compteur-eau-lora` → **Validate** et **Install → Wirelessly**.

## Izar / DME

Les deux familles viennent de Diehl Metering et portent le même code fabricant `DME` dans l'en-tête radio, mais elles n'utilisent **pas le même pilote** :

| | DME | Izar |
|---|---|---|
| Collectivité (retours connus) | **Grand Besançon** | **Grand Belfort** |
| `type_compteur` | `dme_07` (défaut) | `izar` |
| Version dans l'en-tête radio | `0x7b` | `0x78` |
| Protection | wM-Bus / OMS, **en clair** à ce jour | brouillage PRIOS, décodé par le pilote avec les clés Diehl par défaut : **en clair** à ce jour |
| Champ « Statut » | `status` | `current_alarms` (`no_alarm`, `leakage`, `meter_blocked`…) |
| Capteurs en plus | — | index fin du mois dernier, durée de vie de la pile, période d'émission, alarmes précédentes (ajoutés automatiquement, [options/izar.yaml](options/izar.yaml)) |

Champs relevés dans `driver_dme_07.cpp` et `driver_izar.cpp` du composant [SzczepanLeon/esphome-components](https://github.com/SzczepanLeon/esphome-components) (commit `d9abe6f`).

**Réglage**, dans `secrets.yaml` :

```yaml
type_compteur: "izar"     # dme_07 (défaut, Besançon) | izar (Belfort) | auto
```

- `type_compteur` s'applique à ton compteur et, par défaut, à tous les voisins. Un voisin d'une autre famille prend `typecompteurN`.
- `auto` laisse le composant choisir le pilote à chaque trame. C'est pratique pour un mélange, mais les champs propres à un pilote, comme « Statut », peuvent manquer.
- **Dans le doute**, regarde les journaux : chaque trame entendue y est classée `DME` (version `7B`) ou `Izar` (version `78`), y compris pour les compteurs inconnus :
  ```
  [D][csv] Compteur 23456789 (connu, Izar, version 78) RSSI -83 dBm | …
  ```

**Clé AES**, seulement si l'opérateur chiffre les trames, ce qui n'est pas le cas aujourd'hui à Besançon ni à Belfort :

```yaml
aes: "00112233445566778899AABBCCDDEEFF"     # ton compteur (32 caractères hexadécimaux)
aesv1: "…"                                  # voisin 1, aesv2 pour le voisin 2…
```

- Absente ou `""` : trames lues en clair. Il n'y a rien à créer si tu n'en as pas besoin.
- La clé appartient à l'abonné ou à l'opérateur. Ne la publie jamais, et n'utilise celle d'un voisin qu'avec son accord écrit.
- Si l'opérateur active le chiffrement, ou change la clé PRIOS d'Izar, **les voisins sans clé tombent** : leurs trames ne sont plus décodées. Ils repassent alors en « inconnu », avec le numéro et le RSSI, sans index. Ton compteur reste lisible avec ta propre clé.

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
| Conso semaine / Conso mois | L depuis lundi / depuis le 1er du mois (1er index reçu de la période, gardé au redémarrage) |
| Prix de l'eau au m³ | Réglage (€/m³, abonnement non compris), voir [Prix de l'eau](#prix-de-leau) |
| Prix de l'eau | Même valeur en capteur (`EUR/m³`), pour le tableau de bord Énergie |
| Coût aujourd'hui / Coût mois | € = conso × prix au m³ |
| Coût hier, Coût cette semaine, Coût semaine dernière, Coût mois dernier | € = conso de la période × prix au m³ ; la conso d'hier et celles des périodes écoulées sont mémorisées (redémarrable). Après une coupure qui saute une période (plusieurs jours / semaines / mois sans trame), le capteur concerné passe à « inconnu » plutôt que d'afficher une valeur qui ne correspond plus à la période attendue |
| Compteur eau - Dernière trame | Heure de la dernière trame décodée (HA affiche « il y a 3 minutes ») |
| Heures de conso continue | Nombre d'heures consécutives avec consommation |
| Fuite - conso min par heure, Fuite - heures consécutives, Seuil débit anormal, Seuil conso journalière, Compteur silencieux après | Seuils réglables depuis HA (communs à ton compteur et aux voisins ; silencieux : 6 h par défaut) |
| Mode absence | Interrupteur |
| Écran - extinction nocturne, Écran - extinction à, Écran - rallumage à | Interrupteur et heures (0 à 23) de l'extinction de l'OLED, 22 h → 7 h par défaut |
| Bouton de la carte | État du bouton PRG (diagnostic) |
| 6 capteurs « problème » | Voir [Alertes](#détection-de-fuite-et-alertes) |

**Chaque voisin déclaré** (nom = `nomcompteurN`) :

| Entité | Description |
|---|---|
| Nom - Index | m³ |
| Nom - Conso aujourd'hui | L |
| Nom - Débit estimé | L/h, entre deux trames espacées d'au moins 120 s |
| Nom - RSSI, Nom - Dernière trame | Diagnostic |
| Nom - Fuite confirmée, Fuite suspectée (nuit), Débit anormal, Conso journalière anormale, Compteur silencieux | Les mêmes alertes que pour ton compteur, avec les **mêmes seuils** (pas de mode absence pour les voisins) |

### Marqueur stable pour les intégrations

Pour qu'une intégration Home Assistant (par exemple [Tarif-Eau](https://github.com/Mathilde-Team/Tarif-Eau), issue #47) retrouve **l'index du compteur de la maison** sans dépendre de libellés modifiables, ce dépôt s'engage sur deux points, vérifiés à chaque PR par l'étape « Marqueur stable pour les intégrations » du CI :

1. **L'appareil** : dans le registre des appareils de HA, le fabricant est `mathilde-team` et le modèle `compteur-eau-wmbus` (bloc `esphome: project:`). Ces deux valeurs ne dépendent ni du nom de l'appareil (`name`, `friendly_name`) ni d'un renommage dans HA.
2. **Le capteur d'index de la maison** : sur cet appareil, c'est le seul capteur dont le **nom d'origine** (`original_name` du registre des entités) est exactement `Compteur eau - Volume total` (id ESPHome `eau_total`, `device_class: water`, `state_class: total_increasing`, en m³). Le nom d'origine reste le même si l'utilisateur renomme l'entité dans HA.

Les index des voisins sont sur le même appareil, mais leur nom d'origine est `<nom> - Index` : ils ne correspondent jamais au point 2. La version du projet (`1.0.0`) ne fait pas partie du contrat.

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

![Aperçu des écrans OLED (simulation) : index, signaux, alertes, index à 5 chiffres](docs/apercu-ecrans.png)

Simulation des pages : index et conso du jour, signaux WiFi et radio, alertes (2 actives, puis 6 avec « +3 autres »), et index à partir de 1000 m³ (police réduite). Le numéro du compteur est masqué sur l'image.


1. **Index** (police réduite à partir de 1000 m³), **conso du jour** et numéro du compteur.
2. **Signaux** WiFi et wM-Bus : barres (4 niveaux) et dBm. Seuils WiFi : -55 / -67 / -75 / -85 dBm. Seuils radio : -60 / -75 / -90 / -100 dBm.
3. **Alertes actives** (jusqu'à 4 lignes, puis « +N autres »). Cette page est sautée s'il n'y a aucune alerte.

### Extinction la nuit et bouton

**Extinction la nuit** : l'écran s'éteint de **22 h à 7 h** par défaut, pour ménager l'OLED. Règle les heures dans le tableau de bord (carte Actions → Écran de la carte) ou sur la page de l'appareil :
- « Écran - extinction à » (début, inclus) et « Écran - rallumage à » (fin, exclue). La plage peut passer minuit (22 → 7) ou non (13 → 14). Si les deux heures sont égales, l'écran ne s'éteint jamais ;
- « Écran - extinction nocturne » : coupe la fonction (écran toujours allumé).

Si l'ESP ne connaît pas l'heure (ni HA ni Internet), l'écran reste allumé.

**Bouton PRG** (GPIO0, substitution `bouton_pin`) :
- appui le jour : page suivante, et rotation automatique suspendue 30 s pour lire la page ;
- appui la nuit : rallume l'écran 60 s, sur la page en cours.

## Détection de fuite et alertes

Pour ton compteur **et pour chaque voisin déclaré** : mêmes règles, mêmes seuils. Le mode absence ne concerne que ton compteur.

| Alerte | Se déclenche quand |
|---|---|
| Fuite confirmée | La conso de chaque heure atteint au moins `Fuite - conso min par heure` (1 L par défaut) pendant au moins `Fuite - heures consécutives` heures (24 par défaut) |
| Fuite suspectée (nuit) | À 5 h, au moins 3 heures consécutives avec consommation |
| Débit anormal | Débit estimé supérieur à `Seuil débit anormal` (1000 L/h par défaut) pendant 10 min |
| Conso journalière anormale | Conso du jour supérieure à `Seuil conso journalière` (800 L par défaut) |
| Conso pendant absence | `Mode absence` activé et au moins 1 L consommé pendant l'heure écoulée |
| Compteur silencieux | Aucune trame reçue depuis plus de `Compteur silencieux après` heures (6 par défaut). Il faut avoir reçu au moins une trame depuis le démarrage de l'ESP |

La résolution de l'index est de 1 L : le débit estimé est donc grossier pour les petits débits.

Les alertes d'un voisin s'appellent « Dupont - Fuite confirmée »… Le paquet ntfy peut les envoyer sur le sujet de ce voisin (voir [Esphome-Compteur-wmbus-ntfy#5](https://github.com/Mathilde-Team/Esphome-Compteur-wmbus-ntfy/issues/5)).

## Tableau de bord Énergie (eau)

Home Assistant peut suivre la consommation d'eau dans son tableau de bord Énergie ([documentation officielle](https://www.home-assistant.io/docs/energy/water/)). Il calcule lui-même la consommation par heure, jour, semaine et mois à partir de l'**index cumulé** du compteur.

### Quelle entité ajouter

Paramètres → Tableaux de bord → **Énergie** → Consommation d'eau → **Ajouter une source d'eau** → choisir :

`sensor.compteur_eau_lora_compteur_eau_volume_total` (« Compteur eau - Volume total »)

Cette entité a les trois attributs exigés par HA pour l'eau :

| Attribut | Valeur |
|---|---|
| `device_class` | `water` |
| `state_class` | `total_increasing` |
| `unit_of_measurement` | `m³` (avec le ³ en exposant : `m3` est refusé) |

Ne pas ajouter :
- « Conso aujourd'hui », « Conso hier », « Conso dernière heure », « Débit estimé » : ce ne sont pas des index cumulés, HA ne les propose d'ailleurs pas ;
- les index des voisins (`… - Index`) : ils apparaissent dans la liste (mêmes attributs), mais les additionner à ton compteur fausserait ta consommation.

Avec `total_increasing`, si l'index baisse (compteur remplacé), HA démarre un nouveau cycle sans perdre l'historique.

### Débit d'eau (facultatif)

Dans la même fenêtre, le champ **Débit d'eau** (« Water flow rate ») accepte `sensor.compteur_eau_lora_debit_estime` (« Débit estimé »). HA y exige `device_class: volume_flow_rate` ; sans cette classe, il affiche « Classe d'appareil inattendue » (#46). Le capteur la déclare, avec l'unité `L/h`.

### Pourquoi l'unité est écrite dans le YAML

Le composant `wmbus_meter` devrait transformer l'unité `m3` du champ `total_m3` en `m³`. Sa table de correspondance est mal construite : chaque clé commence par une espace (`' m3'`), la recherche échoue et l'unité brute **`m3`** est publiée (même problème pour `dbm` au lieu de `dBm`). Constaté sur le commit `d9abe6f` de `SzczepanLeon/esphome-components`. Le tableau de bord Énergie refuse alors le capteur.

La configuration écrit donc l'unité en dur sur les 5 index et les 5 RSSI :

```yaml
- platform: wmbus_meter
  parent_id: mon_compteur
  field: total_m3
  device_class: water
  state_class: total_increasing
  unit_of_measurement: "m³"
```

### Après la mise à jour du firmware

1. Flashe la nouvelle configuration (OTA : ESPHome Builder → Install → Wirelessly).
2. Outils de développement → États : l'index doit afficher `unit_of_measurement: m³`.
3. Outils de développement → **Statistiques** : HA signale un **changement d'unité** sur l'index (les anciennes statistiques étaient en `m3`). Clique sur **Corriger** et choisis de **mettre à jour l'unité** des statistiques existantes (ou de les supprimer). Tant que ce problème n'est pas réglé, l'entité reste absente de la liste du tableau de bord Énergie.
4. Ajoute l'entité comme source d'eau (voir plus haut).
5. Patiente : les statistiques long terme sont calculées toutes les heures. Les premières barres apparaissent après **1 à 2 h**.

### Si ça ne marche toujours pas

| Symptôme | Piste |
|---|---|
| L'entité n'est pas dans la liste | Unité toujours `m3` (ancien firmware) ou problème non corrigé dans Outils de développement → Statistiques |
| Tableau de bord vide | Moins de 2 h depuis l'ajout, ou aucune trame reçue (index `unknown`) : vérifier l'alerte « Compteur silencieux » |
| Pic énorme un jour donné | Une trame mal décodée a fait baisser puis remonter l'index : corriger la valeur dans Outils de développement → Statistiques |
| Entité absente de l'historique | Exclue du `recorder` dans `configuration.yaml`, ou désactivée |

## Prix de l'eau

Règle **« Prix de l'eau au m³ »** (Réglages du tableau de bord, ou page de l'appareil) avec le prix d'un m³ supplémentaire, **abonnement non compris** : eau potable + assainissement + redevances, TTC. C'est ce prix qui compte pour le coût d'un litre consommé. L'abonnement est fixe : il ne dépend pas de la conso.

Exemple : Grand Besançon Métropole, tarif unique des régies au 1er janvier 2026, tranche 3,1 à 100 m³ ([rapport sur le prix et la qualité des services 2025, conseil communautaire du 24 septembre 2026](https://datasets.grandbesancon.fr/fichiers/delibs/grandBesancon/conseilCommunautaire/2026/20260924/0000C9DA.PDF)) :

| Part | Prix HT | TVA | Prix TTC |
|---|---|---|---|
| Eau potable : part variable 1,38 + redevances « préservation de la ressource » 0,065, « consommation eau potable » 0,39 et « performance des réseaux » 0,03 | 1,865 €/m³ | 5,5 % | ≈ 1,97 €/m³ |
| Assainissement collectif : part variable 1,66 + redevance « performance des systèmes d'assainissement » 0,04 | 1,70 €/m³ | 10 % | ≈ 1,87 €/m³ |
| **Total** | | | **≈ 3,84 €/m³** |

Le même rapport donne 4,04 € TTC/m³ pour une facture type de 120 m³, abonnements compris (484,23 €). Les 3 premiers m³ par an sont gratuits pour les ménages. Les communes encore en délégation de service public peuvent avoir un autre tarif.

**Autres communes** : l'observatoire national des services d'eau et d'assainissement (SISPEA) publie en [données ouvertes](https://www.services.eaufrance.fr/pro/telechargement) les indicateurs de chaque service, dont le prix TTC au m³ pour 120 m³ (indicateur D102.0 pour l'eau potable). Ces données ont un an de décalage, et c'est un prix moyen abonnement compris. Pour un prix exact, prends le prix variable de ta facture ou du rapport annuel de ta collectivité.

**Tableau de bord Énergie** : Paramètres → Tableaux de bord → Énergie → Consommation d'eau → ton index → **Utiliser une entité avec le prix actuel** → `Prix de l'eau` (capteur en `EUR/m³`). Tu peux aussi choisir un prix fixe.

**Conso semaine et mois** : calculées par l'ESP, comme la conso du jour (1er index reçu depuis lundi ou depuis le 1er du mois). Pas besoin de `configuration.yaml` ni de compteur de services publics. Les graphiques « par semaine » et « par mois » utilisent, eux, les statistiques de l'index.

## Tableau de bord « Compteur d'eau »

En plus du tableau de bord Énergie, `ha_dashboard_compteur_eau.yaml` décrit un tableau de bord dédié (vue « Eau », en sections) :

| Section | Contenu |
|---|---|
| En direct | Jauges du débit estimé (vert < 300 L/h < orange < 1000 L/h < rouge) et de la conso du jour (vert < 500 L < orange < 800 L < rouge), tuiles index / dernière heure / hier / heures continues |
| Coûts et périodes | Coût d'aujourd'hui, d'hier, du mois, du mois dernier, de cette semaine et de la semaine dernière, conso de la semaine et du mois, conso **par semaine** (12 semaines) et **par mois** (12 mois) |
| Alertes | Une tuile par alerte active, sinon « ✅ Aucune anomalie détectée », puis le **journal des alertes** sur 7 jours (début et fin de chaque alerte) |
| Historique | Conso du jour et débit sur 24 h, conso **par heure sur 48 h** (hier et aujourd'hui côte à côte), par heure sur 7 jours, **par jour** sur 30 jours, index sur 30 jours |
| Actions | Mode absence (+ boutons ntfy dans le tableau de bord généré, si le paquet est installé) |
| Réglages | Prix de l'eau au m³, seuils de détection, export CSV (activation et intervalle) |
| Diagnostic | Statut du compteur, dernière trame reçue, RSSI radio et WiFi, compteur silencieux |
| Signal | Courbe du RSSI radio et WiFi sur 24 h |

### Générer le tableau de bord avec tes voisins

`scripts/generer_tableau_de_bord.py` part de `ha_dashboard_compteur_eau.yaml` et ajoute une vue **« Voisins »** construite à partir des voisins déclarés dans `compteur-eau-lora.yaml` (noms lus dans `secrets.yaml`) :

| Section | Contenu |
|---|---|
| Tous les compteurs | Conso par jour sur 30 jours (toi + chaque voisin, en barres), RSSI radio de tous les compteurs sur 24 h |
| Une section par voisin | Index, conso du jour, signal radio, dernière trame, débit, ses 5 alertes, conso par jour sur 30 jours |

Depuis la racine du dépôt, à côté de ton `secrets.yaml` :

```bash
uv run --with pyyaml python scripts/generer_tableau_de_bord.py
# ou : pip install pyyaml && python3 scripts/generer_tableau_de_bord.py
```

Il ajuste aussi :
- **les jauges** : max et paliers calculés à partir des seuils d'alerte (débit : orange à 30 % du seuil, rouge au seuil, max à 150 % ; conso du jour : orange à 62,5 %, rouge au seuil, max à 125 %). Il prend les valeurs initiales de la configuration. Si tu as changé un seuil dans HA, passe-le avec `--seuil-debit 1500` ou `--seuil-jour 600` ;
- **la carte Actions** : interrupteur et boutons ntfy (message de test, envoi des bilans), seulement si le paquet ntfy est inclus dans `packages:`.

Le script écrit `ha_dashboard_compteur_eau.genere.yaml`, ignoré par git car il contient les noms des voisins. Relance-le après chaque ajout ou retrait de voisin. Options : `--config`, `--secrets`, `--sortie`, et `--appareil` si ton appareil n'a plus le nom `Compteur Eau LoRa` dans HA.

Avec ESPHome Builder, copie `compteur-eau-lora.yaml` et `secrets.yaml` depuis `/config/esphome/` (File editor ou Samba) vers ton clone du dépôt, ou lance le script avec `--config` et `--secrets` pointant sur le partage Samba.

### Installer le tableau de bord

**Installation** : Paramètres → Tableaux de bord → **Ajouter un tableau de bord** → Nouveau tableau de bord à partir de zéro, titre « Compteur d'eau ». Ouvre-le, puis crayon → ⋮ → **Éditeur de configuration brute**. Remplace tout le contenu par le fichier (`ha_dashboard_compteur_eau.genere.yaml`, ou `ha_dashboard_compteur_eau.yaml` sans vue Voisins) et enregistre.

Remarques :
- Les identifiants d'entités supposent l'appareil nommé `compteur-eau-lora`. Si tu l'as renommé, remplace le préfixe `compteur_eau_lora_`.
- Les graphiques de conso horaire et journalière utilisent la statistique **`change`** (variation de l'index sur la période). Un capteur `total_increasing` n'a que les statistiques `state`, `sum` et `change`, et un capteur `measurement` n'a que `mean`, `min` et `max`. Demander `max` sur l'index ou `state` sur « Conso dernière heure » donne un graphique vide.
- Ces deux graphiques ont besoin que l'index soit en `m³` (voir plus haut). Ils restent vides tant que les statistiques sont en erreur.
- La tuile **« Hier » affiche « Inconnu »** jusqu'au premier minuit après un démarrage de l'ESP : « Conso hier » n'est publiée qu'à minuit. Le graphique « Conso journalière (30 jours) » n'a pas cette limite.

## Export CSV dans Home Assistant

L'ESP ne peut pas écrire de fichier dans HA. Pour **chaque compteur capté** (connu ou inconnu), il envoie donc à HA un évènement `esphome.wmbus_trame`. Celui-ci contient `compteur`, `nom`, `statut`, `rssi_dbm`, `index_m3` et `conso_jour_l` : voir [le script `envoi_trame`](#script-envoi_trame--lévénement-envoyé-à-home-assistant). L'ESP en envoie au plus un par compteur et par « Export CSV - intervalle » (15 min par défaut). Une automatisation HA ajoute la ligne au CSV avec `notify.send_message` et l'intégration **File**.

**Tout se fait dans l'interface de HA, sans modifier `configuration.yaml`**, en écrivant le fichier dans `/media`, dossier autorisé par défaut.

En bref :
1. Autoriser l'appareil ESPHome à effectuer des actions Home Assistant.
2. Ajouter l'intégration File (notification) sur `/media/releves_compteurs.csv`, sans horodatage.
3. Créer l'automatisation [`ha_automation_releves_csv.yaml`](ha_automation_releves_csv.yaml) dans l'éditeur (⋮ → Modifier en YAML), en adaptant l'entité `notify`.

**Tutoriel pas à pas, contrôles, dépannage et variantes : [docs/export-csv-home-assistant.md](docs/export-csv-home-assistant.md).**

```
timestamp;compteur;nom;statut;rssi_dbm;index_m3;conso_jour_l
2026-10-17 08:15:02;12345678;Mon compteur;connu;-41;337,693;12
2026-10-17 08:15:09;99999999;;inconnu;-88;;
```

Exemple avec des numéros fictifs. Pour les compteurs **inconnus**, seuls le numéro et le RSSI sont disponibles : leurs trames sont chiffrées et l'ESP ne les décode pas. Ne place pas le fichier dans `/config/www` : son contenu y serait public, à l'adresse `/local/`.

## Notifications ntfy entre voisins (sans Home Assistant)

Le dépôt compagnon **[Esphome-Compteur-wmbus-ntfy](https://github.com/Mathilde-Team/Esphome-Compteur-wmbus-ntfy)** ajoute des notifications push [ntfy](https://ntfy.sh). L'ESP les envoie **lui-même** en HTTPS : elles ne passent ni par Home Assistant, ni par `notify`, ni par MQTT.

- **Toi** : alertes (fuite confirmée, fuite de nuit, débit anormal, conso élevée, conso pendant une absence, compteur silencieux), fins d'alerte et bilan quotidien. Elles arrivent même si Home Assistant est arrêté.
- **Chaque voisin** : bilan quotidien de **son** compteur (conso du jour + index) et alertes de **son** compteur (fuite, débit, conso élevée, compteur silencieux) sur **son** sujet ntfy. Il le lit dans l'appli ntfy (Android, iOS, navigateur) ou dans sa propre domotique (Home Assistant, Jeedom, Domoticz, openHAB, Node-RED… : tout ce qui sait lire un flux HTTP JSON, SSE ou WebSocket). Un voisin n'a besoin d'**aucune** installation chez lui.

Mise en place, en résumé :

1. Un sujet aléatoire par personne dans `secrets.yaml` (`ntfy_topic_moi`, `ntfy_topic_v1`…, `""` = rien). Sur ntfy.sh, **le nom du sujet sert de mot de passe**.
2. `ntfy_topic_moi: !secret ntfy_topic_moi` ajouté aux `substitutions` de `compteur-eau-lora.yaml`.
3. Le paquet, puis une ligne par voisin (même `i` que sa ligne `voisins/voisin.yaml`), ajoutés à `packages:` :
   ```yaml
   packages:
     ntfy: github://Mathilde-Team/Esphome-Compteur-wmbus-ntfy/ntfy.yaml@main
     ntfy_voisin1:
       url: https://github.com/Mathilde-Team/Esphome-Compteur-wmbus-ntfy
       ref: main
       files:
         - path: ntfy-voisin.yaml
           vars: { i: 1, nom: !secret nomcompteur1, topic: !secret ntfy_topic_v1 }
   ```
4. Flash, puis bouton **« ntfy - message de test »**.

Détails (contenu des messages, priorités, abonnement depuis une autre domotique, serveur ntfy privé, limites de ntfy.sh) : voir le [README du dépôt ntfy](https://github.com/Mathilde-Team/Esphome-Compteur-wmbus-ntfy#readme).

## Prévenir les voisins (extension)

L'automatisation construit d'abord la ligne (`ligne`), puis l'envoie : il suffit d'ajouter une action après `notify.send_message`. Le fichier contient un bloc commenté prêt à l'emploi pour **MQTT** : un topic par compteur, compteurs connus seulement. On peut aussi utiliser `notify.mobile_app_…`, Telegram, un e-mail ou ntfy. Chaque voisin ne doit recevoir que **son** compteur : un topic et des droits de broker par voisin. Voir [Prévenir les voisins](docs/export-csv-home-assistant.md#prévenir-les-voisins).

## Dépannage

| Symptôme | Piste |
|---|---|
| Log : `Telegram not handled by any handler` | Trame d'un compteur non déclaré. Normal pour les compteurs des autres. Pour en lire un, ajoute son numéro dans `secrets.yaml` |
| Trames d'un compteur reçues mais index vide | Vérifier le `type` (driver) et la clé de chiffrement éventuelle (option `key` du composant `wmbus_meter`, voir sa documentation) |
| Écran noir au démarrage | Vext doit être allumé avant l'init de l'OLED : c'est le rôle de `on_boot` (priorité 799). Ne pas la modifier |
| Conso du jour à 0 | Normal avant la 2e trame de la journée (la 1re fixe le « 1er index du jour »). Sinon, regarde dans les journaux de l'ESP les lignes `[conso]` : « 1er index du jour », « Conso du jour : … L » ou « Heure non synchronisée avec HA » |
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

## Contribuer

Le dépôt suit le socle qualité de Mathilde-Team :

- **`main`** = branche de livraison, **`dev`** = branche d'intégration. On ne pousse jamais directement sur l'une ou l'autre.
- Une branche par sujet, créée depuis `dev` (`feat/<n°>-…`, `fix/<n°>-…`, `docs/…`, `ci/…`), puis une **PR vers `dev`**.
- Livraison : **PR `dev` → `main`**. Le check « Garde : PR vers main doit venir de dev » refuse toute autre branche source.
- La CI (« Qualité (lint, validation ESPHome) ») doit passer : `yamllint --strict` et `esphome config`. Une compilation complète tourne sur `main` et à la demande.
- Les protections de `main` et `dev` sont versionnées dans `.github/branch-protection/`. Le workflow « Protection des branches » signale chaque jour tout écart.

## Licence

[MIT](LICENSE) © 2026 Mathilde Deuscher.

## Crédits

[ESPHome](https://esphome.io), [Home Assistant](https://www.home-assistant.io), [SzczepanLeon/esphome-components](https://github.com/SzczepanLeon/esphome-components) pour le décodage wM-Bus, [Material Design Icons](https://pictogrammers.com/library/mdi/) pour les pictogrammes de l'écran.
