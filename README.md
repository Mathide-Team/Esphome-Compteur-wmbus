# Compteur d'eau wM-Bus → ESPHome → Home Assistant

Lecture radio (wM-Bus, mode T1, 868,95 MHz) du compteur d'eau de la maison **et** de compteurs voisins, avec une carte ESP32-S3 équipée d'une radio SX1262 et d'un écran OLED. Les mesures remontent dans Home Assistant (HA) ; HA écrit un fichier CSV des relevés et pourra prévenir les voisins (MQTT, notification…).

## Ce que fait le projet

- **Ton compteur** : index, RSSI, statut, débit estimé, conso de la dernière heure / du jour / d'hier, détection de fuite et alertes.
- **Jusqu'à 4 compteurs voisins** : index, conso du jour et RSSI de chacun (pas d'alertes).
- **Écran OLED** (compteur de la maison) : 3 pages qui tournent toutes les 5 s.
- **Compteurs inconnus** : tous les compteurs captés par la radio, déclarés ou non, sont aussi envoyés à HA sous forme d'événement (numéro + RSSI).
- **Export CSV** : HA ajoute une ligne par compteur (au plus une par intervalle réglable, 15 min par défaut) à un fichier CSV. Un script Python extrait aussi un CSV à partir des logs ESPHome.

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

La coque est vendue pour la V3 de la carte. Vérifie que la V4 rentre bien avant de la fermer : position de l'écran, du connecteur USB-C et du connecteur d'antenne.

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

Pour avoir moins de 4 voisins, voir [Adapter la configuration](#adapter-la-configuration). Si un voisin a un autre modèle de compteur, change son `type` dans `wmbus_meter`.

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

L'appareil est découvert par l'intégration ESPHome. Pour le CSV, voir [Export CSV](#export-csv-dans-home-assistant).

## La configuration ESPHome expliquée

Cette section suit `compteur-eau-lora.yaml` bloc par bloc, dans l'ordre du fichier.

### `substitutions` : les variables du fichier

```yaml
num_compteur: !secret compteur0
nom_moi: "Mon compteur"
num_v1: !secret compteur1
nom_v1: !secret nomcompteur1
...
mdi_url: "https://github.com/Templarian/MaterialDesign-Webfont/raw/v7.4.47/..."
```

- `${num_compteur}`, `${num_v1}`… `${num_v4}` : numéros des compteurs, lus dans `secrets.yaml`. ESPHome les remplace partout dans le fichier : `meter_id` de `wmbus_meter`, liste des compteurs connus dans `on_frame`, numéro affiché à l'écran.
- `${nom_v1}`… : noms des voisins. Ils servent à nommer les entités HA (« Dupont - Index »…) et la colonne `nom` de l'événement CSV.
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

### `time` : l'heure de Home Assistant et les tâches planifiées

L'heure vient de HA (`platform: homeassistant`). Deux tâches tournent à heure fixe :

**Chaque heure pile** (`minutes: 0, seconds: 0`) :
1. Conso de l'heure = (index actuel − index au début de l'heure) × 1000 → capteur « Conso dernière heure ».
2. Si cette conso atteint au moins le seuil `Fuite - conso min par heure`, le compteur d'heures consécutives `g_leak_hours` augmente de 1. Sinon, il revient à 0 et le drapeau de fuite de nuit est effacé.
3. À **5 h**, si au moins 3 heures de conso d'affilée sont comptées, `g_night_flag` passe à vrai (alerte « Fuite suspectée (nuit) »).

**Chaque jour à minuit** :
1. « Conso hier » = dernier index reçu − 1er index de la veille. Le jour de la veille est calculé à partir de minuit moins 1 h.
2. Les capteurs « Conso aujourd'hui » (toi + 4 voisins) sont recalculés et retombent à 0 jusqu'à la première trame du nouveau jour.

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
| `vN_total`, `vN_day_start`, `vN_day` | Pareil pour chaque voisin N (index, 1er index du jour, jour) | oui (sauf `vN_total`) |
| `g_id_off` | Position du numéro de compteur dans l'en-tête des trames (4 ou 6), apprise automatiquement | oui |
| `g_csv_last` | Pour chaque numéro de compteur, l'instant du dernier événement CSV envoyé | non |
| `g_ev_nom`, `g_ev_index`, `g_ev_conso` | Valeurs préparées pour l'événement envoyé à HA | non |

`restore_value: yes` enregistre la valeur en flash : un redémarrage dans la journée ne fait pas perdre le 1er index du jour.

### `output` : la sortie Vext

`GPIO36` avec `inverted: true` : Vext est **actif à l'état bas**. `turn_on` met donc la broche à 0 V, ce qui alimente l'OLED et l'étage RF.

### `external_components` : le composant wM-Bus

`SzczepanLeon/esphome-components@main` fournit `wmbus_radio` (pilote de la radio SX1262), `wmbus_meter` (déclaration des compteurs) et `wmbus_common` (décodage, drivers comme `dme_07`). La branche `main` peut évoluer : en cas de souci après une mise à jour, fige une version (`@<tag>` ou `@<commit>`).

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

- Un bloc pour toi, puis un par voisin. `type: dme_07` est le driver des compteurs d'eau DME. Change-le si un voisin a un autre modèle.
- `mode: [T1]` : mode wM-Bus T1 (émission seule du compteur, 868,95 MHz), celui des compteurs d'eau.
- `meter_id` doit être un numéro précis (pas de joker) : **seuls les compteurs déclarés ici voient leur index décodé**. Les autres ne remontent que leur numéro et leur RSSI.
- Si un compteur a une trame chiffrée, ajoute sa clé avec l'option `key:` (voir la documentation du composant).

### `script` `envoi_trame` : l'événement envoyé à Home Assistant

Paramètres : `p_id` (numéro sur 8 chiffres hexadécimaux), `p_rssi` (dBm), `p_slot` (−1 = inconnu, 0 = toi, 1 à 4 = voisins). `mode: parallel` : plusieurs compteurs peuvent être traités en même temps.

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
- `WiFi RSSI` : force du signal WiFi, toutes les 30 s.
- Capteurs `template` : `Débit estimé` (L/h), `Conso dernière heure`, `Conso hier`, `Heures de conso continue`, `Conso aujourd'hui` (recalculée toutes les 60 s, 0 par défaut).

**Chaque voisin** (blocs « Voisin 1 » à « Voisin 4 ») : `Nom - Index` (avec la même logique de 1er index du jour), `Nom - RSSI` et `Nom - Conso aujourd'hui`.

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

**Moins de 4 voisins** : pour le voisin N, supprime :
- `num_vN` / `nom_vN` dans `substitutions` ;
- son bloc dans `wmbus_meter` (`compteur_vN`) ;
- ses 3 variables `vN_*` dans `globals` ;
- ses 3 capteurs dans `sensor` (`vN_index`, `vN_rssi`, `vN_conso_jour`) ;
- la ligne `id(vN_conso_jour).update();` de la tâche de minuit (`time`) ;
- la ligne `strtoul("${num_vN}"…)` dans le tableau `connus` de `on_frame`, en réduisant la taille du tableau et la boucle (`connus[5]`, `i < 5`) ;
- le `case N:` du script `envoi_trame` ;
- `compteurN` / `nomcompteurN` dans `secrets.yaml`.

**Autre carte** : adapte les broches de `spi`, `wmbus_radio`, `i2c`, `display` et `output` (Vext). Si la carte n'a pas de Vext, supprime `output` et `on_boot`.

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

**Principe** : l'ESP ne peut pas écrire de fichier dans HA. Il envoie donc à HA, pour **chaque compteur capté** (connu ou inconnu), un événement `esphome.wmbus_trame` contenant `compteur` (8 chiffres, sans `0x`), `nom`, `statut`, `rssi_dbm`, `index_m3` et `conso_jour_l` (voir [le script `envoi_trame`](#script-envoi_trame--lévénement-envoyé-à-home-assistant)). Il en envoie au plus un par compteur pendant la durée « Export CSV - intervalle » (15 min par défaut, réglable depuis HA). Une automatisation HA ajoute alors une ligne au CSV avec l'action `notify.send_message` de l'intégration **File**.

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
6. **Vérifier** : Outils de développement → Événements → écouter `esphome.wmbus_trame`.

Ne place pas le fichier dans `/config/www` : son contenu serait accessible sans authentification à l'adresse `/local/`.

Exemple de fichier obtenu (numéros fictifs) :

```
timestamp;compteur;statut;rssi_dbm;index_m3;conso_jour_l
2026-10-17 00:42:17;12345678;connu;-40;337,693;12
2026-10-17 00:42:19;23456789;connu;-61;1204,512;85
2026-10-17 00:42:20;99999999;inconnu;-70;;
```

> **Attention** : `ha_automation_releves_csv.yaml` écoute encore `esphome.wmbus_frame` et lit `trigger.event.data.rssi`. Remplace-les par `esphome.wmbus_trame` et `trigger.event.data.rssi_dbm`, sinon l'automatisation ne se déclenche pas.

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
