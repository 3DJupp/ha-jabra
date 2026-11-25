# Status (updated 25.11.2026)

The repository now contains the first implementation (phases 1 to 4 of the original plan, without
hardware): `jabra2mqtt` bridge, tests against a fake jabridge and an in-process MQTT broker, add-on
configuration, Docker image and CI. Correction to the research below: jabridge **does** expose the
busylight through IPC (`device.busylight`, modes `auto`, `on`, `off`; only `auto` needs PipeWire).
Open: everything that needs real hardware, rename and PIN, a firmware update trigger.
The "first task for Claude Code" at the end of this file has been done; see `CLAUDE.md` for the
current rules and `docs/HARDWARE_TESTING.md` for the next step.

---

# Original research and plan (German, 25.11.2026)

Stand: 25.11.2026. Zielgerät: Jabra Evolve2 85 (Dominic hat dieses Modell; das ältere Evolve 85 ist ein anderes Gerät). Alles hier ist Recherchestand aus Web und GitHub, keine Hardware wurde getestet.

## 1. Ziel

Ein Home-Assistant-Add-on (oder zunächst ein eigenständiger Dienst), das Jabra-Headsets und Dongles in HA verfügbar macht:

1. Akkustand und Ladestatus als Sensoren
2. Busylight als Schalter, steuerbar aus HA-Automationen
3. Status: verbunden, im Call, Mute, Firmware-Version
4. Parameter des Headsets lesen und ändern (ANC, HearThrough, Equalizer und so weiter)
5. Gerät umbenennen, PIN setzen (Machbarkeit offen, siehe Abschnitt 7)
6. Firmware: Update-Verfügbarkeit anzeigen, Installation nur mit ausdrücklicher Bestätigung

Nicht Ziel: eigene Custom-Firmware. Dazu gibt es keine Vorarbeiten für den Evolve2 85.

## 2. Befunde (mit Belegstatus)

### Belegt

- Der Evolve2 85 bekommt noch Firmware. Letzte Version laut Jabra: 1.5.7 vom 28.07.2025 (Bluetooth-Verschlüsselung auf 128 Bit). Verkauf wurde am 20.02.2024 eingestellt (laut Händlerseite CDW). Danach läuft die Wartungsphase bis Garantieende, danach EOL.
- jabridge (https://github.com/Watchdog0x/jabridge, Apache-2.0, Go) ist ein Community-Ersatz für Jabra Direct unter Linux.
  - Reines Go, kein cgo, kein libjabra.so. Das GNP-Protokoll wurde aus Jabras Updater und libjabra.so rekonstruiert.
  - Läuft als Dienst mit lokalem JSON-RPC-2.0-Socket (`$XDG_RUNTIME_DIR/jabridge.sock` oder `JABRIDGE_SOCKET`). Newline-getrennte JSON-Objekte.
  - Methoden laut Doku: `service.ping`, `service.capabilities`, `subscribe`, `devices.list`, `device.select`, `device.battery`, `device.firmware`, `settings.list`, `settings.set`, `bt.list`, `sound.*`, `buttons.status`.
  - Events: `device.attached`, `device.detached`, `device.battery.update`, `device.pairing.update`, `device.button`, `device.signal`, `sound.changed`. Nicht jedes Modell sendet jeden Event.
  - `settings.set` verlangt `device`, `key`, `value`, den vollständigen `target` und den alten Wert als `previous` aus `settings.list`. Nie automatisch wiederholen, bei Timeout erst neu lesen.
  - Für Evolve2 85 sind laut Code schreibbar: Geräuschmodus (Aus, HearThrough, ANC) und HearThrough-Pegel. Equalizer, Noise-Button-Zyklus und Power Saving sind bei passendem Firmware-Profil editierbar, aber nur teilweise an echter Hardware geprüft.
  - Busylight: Es gibt einen `BusylightController` mit Modi auto, on, off. Auto folgt der PipeWire-Call-Erkennung. Über IPC ist `device.busylight` im Handler vorhanden (in der IPC-Doku nicht aufgeführt).
  - Firmware-Installation ist ein eigener exklusiver Workflow und ausdrücklich keine IPC-Methode. Neben dem laufenden Dienst darf kein anderer Prozess HID-Geräte öffnen.
  - Native Einstellungen über direktes System-Bluetooth sind nicht implementiert. Zugriff läuft über USB oder über einen Jabra-Link-Dongle.
  - Ein Nutzer berichtet erfolgreiches Pairing eines Evolve2 85 mit dem Link 380c (USB 0b0e:24c9). Weitere Steuerung über diesen Dongle ist laut README eingeschränkt.
- jLink (https://github.com/madi-ppi/jLink) nutzt Jabras offizielles SDK (libjabra, C-Header liegen im Repo). Demo: Evolve2 85 von 1.3.8 auf 1.5.4 per `Jabra_Evolve2_85-v1.5.4-ev285t-vector.zip`, USB-ID `0b0e:24ba` ("Jabra Evolve2 85 UC Data").
- Jabra SDK enthält unter anderem: `Jabra_GetBatteryStatusV2`, `Jabra_SetBusylightStatus` / `Jabra_GetBusylightStatus`, `Jabra_GetSettings` / `Jabra_SetSettings` (GUID-basiert), `Jabra_CheckForFirmwareUpdate`, `Jabra_GetUserDefinedDeviceName` (nur lesen gefunden), Pairing-Funktionen (`Jabra_SetBTPairing`, `Jabra_GetPairingList`, `Jabra_ClearPairingList`).
- fwupd hat ein Plugin `jabra-gnp` für offizielle Firmware-Updates einiger Jabra-Geräte (Linux).
- Jabras Hard-Mute: Beim Evolve2 85 mutet das Hochklappen des Mikrofonarms fest. Der Zustand lässt sich per Library nicht aufheben.

### Nicht belegt, ausdrücklich offen

- Ob der Evolve2 85 per BLE-GATT etwas Brauchbares anbietet (Akku-Service 0x180F, herstellerspezifische Services). HA und ESPHome Bluetooth Proxy können nur BLE, kein Bluetooth Classic.
- Ob Umbenennen und PIN im Protokoll existieren. Im SDK wurde nur Lesen des Gerätenamens gefunden und kein PIN-Setter. Möglicherweise stecken beide in der Geräteeinstellungs-Datenbank, die Jabra Direct aus der Cloud lädt.
- Ob `jabridge service` ohne systemd und ohne PipeWire in einem Container läuft.
- Welche Funktionen über den Link-Dongle statt per USB-Kabel funktionieren.

### Nicht beschaffbar im Workspace

jabra.com, developer.jabra.com und APK-Mirrors waren gesperrt. Benötigt von Dominic:
- Sound+ APK (aus seinem Handy oder Backup)
- Firmware-ZIP des Evolve2 85 (aus dem Jabra-Direct-Cache oder Jabra-Support)
- Optional Jabra SDK von developer.jabra.com
Diese Dateien niemals ins öffentliche Repo einchecken (Urheberrecht).

## 3. Architektur

Kernproblem: Die Steuerung läuft über USB-HID an dem Rechner, an dem das Headset oder der Link-Dongle steckt. Ein HA-Add-on kann nur Geräte nutzen, die am HA-Host hängen. Das Headset sitzt aber meist am Arbeitsplatz-PC.

Optionen:

- **A. Dongle am HA-Host.** Link 380 steckt am HA-Host (oder per USB-Passthrough in der HAOS-VM, falls HAOS unter Proxmox läuft; zu klären). Das Headset koppelt sich zusätzlich an diesen Dongle. Unsicher, wie viel GNP-Steuerung über den Dongle geht.
- **B. Eigener Bridge-Dienst auf dem Rechner mit USB-Zugang.** Läuft auf dem PC oder einem kleinen Linux-Host (zum Beispiel Pi) und spricht mit jabridge. Veröffentlicht per MQTT mit HA-Discovery an den bestehenden Broker (HiveMQ CE in LXC 202). Das Add-on ist dann optional.
- **C. USB/IP.** Dongle wird per usbip an den HA-Host durchgereicht. Funktioniert, ist aber fragil.

**Empfehlung:** Zuerst B als eigenständiger Container oder Systemdienst (`jabra2mqtt`), weil er sich ohne Add-on-Hürden entwickeln und testen lässt. Danach ein dünnes HA-Add-on um dasselbe Image, mit `usb: true`, passendem `devices` für `/dev/hidraw*` und Abhängigkeit vom MQTT-Service. So lassen sich A und B mit demselben Code bedienen.

Die PipeWire-Call-Erkennung von jabridge fällt im Add-on weg. In HA wird das Busylight stattdessen aus Automationen gesteuert (zum Beispiel Kalender, Teams-Status, Mikrofon-Sensor der Companion-App). Das ist ein Vorteil: Präsenzlogik liegt in HA.

## 4. Entitätsmodell (MQTT Discovery)

Pro Gerät ein HA-Device (Identifier: Seriennummer, Modell, Firmware als `sw_version`).

| Entität | Typ | Quelle |
|---|---|---|
| Akku | sensor (battery, %) | `device.battery` und Event `device.battery.update` |
| Lädt | binary_sensor | `device.battery` |
| Verbunden | binary_sensor | `device.attached` / `device.detached` |
| Busylight | switch | GNP-Sender oder jabridge (offen) |
| Im Call | binary_sensor | Events/Signale, falls vorhanden (offen) |
| Mute | binary_sensor | `device.signal` (offen) |
| Geräuschmodus | select | `settings.list` / `settings.set` (noise-control) |
| HearThrough-Pegel | number | `settings.list` / `settings.set` |
| Firmware installiert | sensor | `device.firmware` |
| Update verfügbar | binary_sensor | Prüfung gegen Jabra-Katalog (nur lesen) |
| Gerätename | text | nur wenn Schreiben belegt ist, sonst read-only |

Alle schreibbaren Entitäten hängen an `settings.list`. Der Dienst baut Select/Number/Switch dynamisch aus den zurückgegebenen Choices, `support.state` und `editable`. Nur `available` wird als schreibbar veröffentlicht.

## 5. Sicherheitsregeln für Schreibzugriffe und Firmware

1. Firmware nie automatisch installieren. Nur Prüfung der Verfügbarkeit als Entität. Installation per separatem, bewusst ausgelösten Vorgang (zum Beispiel Button mit Bestätigung oder CLI-Aufruf auf dem Host).
2. Vor Installation: offizielles ZIP mit Prüfsumme, Modell und USB-ID abgleichen, Gerät per Kabel, Akku voll. jabridge hat diese Preflight-Checks eingebaut und sie nicht umgehen.
3. Für den Evolve2 85 ist ein vollständiges Update nur über jLink dokumentiert. Für jabridge ist es nicht als hardwaregeprüft markiert. Erst in einer Testphase an Dominics eigenem Gerät.
4. Bei `settings.set`: immer `previous` und `target` aus dem letzten `settings.list` mitsenden. Kein automatisches Retry. Nach Timeout erst neu lesen.
5. Reset-Funktionen (`device.reset`, Bound-Reset) nicht in HA exponieren.
6. Der Socket ist lokal und unauthentifiziert. Nie ins Netz legen.

## 6. Phasen

**Phase 0: Beschaffung und Analyse (Dominic liefert Dateien)**
- Sound+ APK mit `jadx` und `apktool` untersuchen: Kommunikationsweg (BLE-GATT, RFCOMM, Cloud-Katalog), Befehle für Name und PIN, Busylight.
- Firmware-ZIP mit `binwalk` zerlegen (nur Struktur, Verschlüsselung, Metadaten).
- BLE-Scan mit nRF Connect am eingeschalteten, ungekoppelten Headset: Services und Battery Service notieren.
- Optional USB-Mitschnitt von Jabra Direct (Windows: USBPcap und Wireshark) beim Umbenennen, Busylight, Parameter ändern.

**Phase 1: Proof of Concept auf Linux-Host mit USB**
- jabridge installieren (Release laden, `./jabridge setup`, `./jabridge service start`), `jabridge ipc devices`, `ipc settings headset`, `ipc watch` gegen das Evolve2 85 prüfen.
- Dokumentieren, was am Evolve2 85 per USB-Kabel und was per Link 380 funktioniert.

**Phase 2: `jabra2mqtt`**
- Kleiner Dienst (Go oder Python), der den jabridge-Socket per JSON-RPC nutzt, Events abonniert, periodisch neu liest und per MQTT Discovery veröffentlicht.
- Reconnect, Ping alle ca. 15 Sekunden, Zustand nach Reconnect neu laden, Events nicht als vollständig betrachten.
- Tests gegen einen Mock des jabridge-Sockets (ohne Hardware).

**Phase 3: Busylight und Parameter**
- Busylight-Pfad klären (IPC erweitern oder jabridge forken, da `internal/`-Pakete nicht extern importierbar sind). Upstream-PR anstreben.
- Select/Number-Entitäten aus `settings.list`.

**Phase 4: HA-Add-on**
- `config.yaml` mit `usb: true`, `devices`, `services: mqtt:need`, Multi-Arch-Image, Start über bashio. Pfad für `JABRIDGE_SOCKET` setzen. udev-Regeln im Host nötig (jabridge setup legt Regeln an; im Add-on über Gerätezuweisung lösen).
- Klären, ob der jabridge-Dienst ohne systemd und PipeWire startet. Falls nicht, nur den HID-Teil verwenden oder patchen.

**Phase 5: Optional**
- Umbenennen, PIN, Firmware-Update-Auslöser, abhängig von Phase 0.

## 7. Offene Fragen an Dominic

1. Läuft HAOS als VM unter Proxmox (USB-Passthrough möglich) oder auf eigener Hardware?
2. Hängt das Headset meist am Arbeitsplatz-PC oder an einem Link-Dongle? Soll ein Dongle am HA-Host zusätzlich dazukommen?
3. Welche Mindestfunktion zählt zuerst: Akku, Busylight oder Parameter?
4. Welcher Rechner soll den Bridge-Dienst hosten (Pi5 Mediacenter, Proxmox-LXC mit USB-Passthrough, Arbeits-PC)?
5. Sollen Name und PIN Pflicht sein, oder reicht Read-only, falls sie nicht belegbar sind?

## 8. Erster Auftrag für Claude Code (kopierbar)

> Lies `jabra-ha-addon-plan.md`. Lege ein neues Repo `jabra2mqtt` an. Starte mit Phase 2 gegen einen Mock des jabridge-JSON-RPC-Sockets: Verbindung, `subscribe`, `devices.list`, `device.battery`, `settings.list`, `settings.set` mit `previous`/`target`, Reconnect und Ping. Veröffentliche per MQTT Discovery nur Akku, Verbunden, Firmware sowie Select/Number aus `settings.list` mit `support.state == available`. Schreibe Tests mit aufgezeichneten Beispielantworten. Keine Firmware-Installation, keine Reset-Befehle, kein Retry bei Schreibfehlern. Jabra-Binaries und Firmware nicht ins Repo. Lizenz Apache-2.0 mit Hinweis auf jabridge.

Empfohlene Dateien im Repo: `CLAUDE.md` (Regeln aus Abschnitt 5 und der Hinweis, nie Jabra-Dateien einzuchecken), `docs/protocol-notes.md`, `docs/entities.md`, `tests/fixtures/` für aufgezeichnete IPC-Antworten.

## 9. Quellen

- jabridge: https://github.com/Watchdog0x/jabridge (README, docs/IPC.md, docs/FIRMWARE.md, docs/USAGE.md, CHANGELOG, `daemon/busylight.go`, `cmd/jabridge/choice_settings.go`)
- jLink: https://github.com/madi-ppi/jLink (SDK-Header in `headers/`)
- fwupd jabra-gnp: https://chromium.googlesource.com/chromiumos/third_party/fwupd/+/refs/heads/stabilize-15786.48.B/plugins/jabra-gnp
- Jabra Release Notes Evolve2 85: https://www.jabra.com/support/release-notes/release-note-Jabra-Evolve2-85
- Jabra Developer Docs, Mute: https://developer.jabra.com/site/global/docs/call-control/mute.gsp
- Jabra EOL-Policy: https://www.jabra.com/supportpages/jabra-business-end-of-life-information
- Airoha RACE (nur Kontext, Evolve2 85 nicht als betroffen belegt): https://app.media.ccc.de/v/39c3-bluetooth-headphone-jacking-a-key-to-your-phone
- Bose NC 700 als Vorbild für Update-Analyse: https://github.com/iclemens/bose
