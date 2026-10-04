# Irrigation Scheduler für Home Assistant

Custom Integration für eine automatische Bewässerung einer Zone.

## Features

- **Zeitfenster pro Wochentag**: `von`/`bis` als `time` Entities (Standard 06:00 bis 22:00). Erster Lauf bei `von`, dann alle *n* Stunden (1 bis 24), solange der Start vor `bis` liegt. Beispiel Montag 07:00 bis 22:00, Intervall 6h: 07:00, 13:00, 19:00. Ein Lauf darf über `bis` hinaus dauern. Ist `bis` kleiner oder gleich `von`, geht das Fenster über Mitternacht (z.B. 22:00 bis 04:00); diese Läufe zählen zum Starttag.
- **Modus statisch / dynamisch** (Panel oder Optionen, die Werte beider Modi bleiben gespeichert):
  - *Statisch*: fester Zeitplan, Lauf wird übersprungen, wenn im Vorhersagefenster genug Regen erwartet wird.
  - *Dynamisch*: vor jedem geplanten Lauf wird geprüft
    - Bodenfeuchte (optional, 1 bis n Sensoren): liegt der Durchschnitt auf oder über der Schwelle (Default 60 %), wird übersprungen.
    - Regen in den letzten 30 min: aus einem Regensensor (binär, mm oder mm/h) oder, ohne Sensor, aus dem Zustandsverlauf der Wetter-Entity (Recorder).
    - Regen in der nächsten Stunde: stündliche Vorhersage mit eigenen Schwellen (Default 0,5 mm / 60 %).
    - Bei Regen wird der Lauf um 1 h verschoben und erneut geprüft, solange er im Tagesfenster und vor dem nächsten regulären Slot bleibt; sonst übersprungen. Die Verschiebung übersteht einen Neustart.
    - Alle Zeiten und Schwellen sind einstellbar. Der Schalter "Regenprüfung" schaltet die Regen-Checks in beiden Modi ab.
- **Einzelne Läufe überspringen**: Das Panel listet die geplanten Läufe der nächsten 7 Tage; jeder lässt sich überspringen und wieder aktivieren (beide Modi). "Nächster Lauf" zeigt den nächsten nicht übersprungenen Lauf, übersprungene erscheinen im Verlauf.
- **Dauer pro Wochentag**: 7 `number` Entities (Minuten, `0` = an diesem Tag nicht bewässern). Die Dauer gilt pro Lauf.
- **Regenprüfung**: vor jedem geplanten Lauf wird `weather.get_forecasts` (stündlich, sonst täglich) der gewählten Wetter-Entity abgefragt. Übersprungen wird, wenn im Vorhersagefenster die Regenmenge oder die maximale Regenwahrscheinlichkeit die Schwelle erreicht. Schwelle `0` deaktiviert das jeweilige Kriterium.
- **Ventil**: `switch`, `valve` oder `input_boolean`.
- **Wasserverbrauch (optional)**: Ein Sensor des Bewässerungscomputers wird pro Lauf ausgewertet. Zählerstand (L, m³, gal, ...) wird als Differenz Start/Ende gerechnet und 90 s nach Ende nochmals gelesen, weil Zigbee-Geräte verzögert melden. Ein Zähler-Reset während des Laufs wird erkannt. Durchfluss (L/min, m³/h, ...) wird über die Laufzeit integriert.
- **Wasserkosten**: Wasser- und Abwasserpreis pro m³ (Währung aus den HA-Einstellungen), Abwasser abschaltbar (z.B. bei separatem Gartenzähler). Kosten werden pro Lauf mit dem Tarif zum Laufzeitpunkt gespeichert. Benötigt einen Wassersensor. Im Panel berechnet "Kosten rückwirkend berechnen" Läufe mit Wassermenge, aber ohne Kosten (z.B. von vor der Tarif-Einrichtung), mit dem aktuellen Tarif; bereits berechnete Kosten bleiben unverändert.
- **Neustart-sicher**: Läuft beim HA-Neustart eine Bewässerung, wird das Ende wiederhergestellt bzw. das Ventil geschlossen, falls das Ende bereits verstrichen ist.

## Sidebar-Panel

Die Integration registriert ein Panel **Bewässerung** in der Sidebar (nur für Admins):

- **Status**: aktueller Zustand, nächster/letzter Lauf, Regenvorhersage, manuell bewässern (Minuten frei wählbar) und stoppen.
- **Einstellungen**: Automatik, Regenprüfung, Ventil, Wetter-Entity, Intervall, Regenschwellen, Vorhersagefenster.
- **Wochenplan**: Montag bis Sonntag mit Dauer, von, bis und Vorschau der Startzeiten.
- **Verlauf**: bewässerte Minuten pro Tag (30 Tage) und Tabelle aller Läufe inkl. übersprungener Läufe mit Regenwerten und, falls konfiguriert, Wassermenge. Aufbewahrung 90 Tage.

Bei mehreren Zonen gibt es oben Tabs pro Zone.

## Entities

| Entity | Beschreibung |
| --- | --- |
| `switch.*_automatik` | Automatischer Scheduler an/aus |
| `switch.*_regenprufung` | Regenprüfung für geplante Läufe an/aus |
| `switch.*_bewasserung` | Manuell starten (Dauer des heutigen Tages, ohne Regenprüfung) / stoppen |
| `number.*_<tag>_dauer` | Dauer pro Wochentag in Minuten |
| `time.*_<tag>_von` / `time.*_<tag>_bis` | Zeitfenster pro Wochentag |
| `sensor.*_status` | `idle`, `watering`, `skipped_rain`, `skipped_no_duration`, `error` |
| `sensor.*_nachster_lauf` / `_letzter_lauf` | Zeitstempel |
| `sensor.*_dauer_nachster_lauf` | Dauer des nächsten Laufs |
| `sensor.*_regenvorhersage` / `_regenwahrscheinlichkeit` | Summe mm / max. % im Vorhersagefenster (alle 30 min aktualisiert) |
| `sensor.*_wasser_letzter_lauf` / `_wasser_gesamt` | Nur mit Wassersensor: Liter des letzten Laufs / Gesamtzähler (`total_increasing`, Energy-Dashboard-tauglich) |
| `sensor.*_wasserkosten_gesamt` | Nur mit Wassersensor: aufsummierte Kosten (`monetary`, `total`) |
| `binary_sensor.*_regen_erwartet` | Würde der nächste Lauf wegen Regen übersprungen |

## Installation

HACS: Repository als *Custom repository* (Typ *Integration*) hinzufügen, oder `custom_components/irrigation_scheduler` nach `<config>/custom_components/` kopieren. Danach HA neu starten und unter *Einstellungen > Geräte & Dienste* "Irrigation Scheduler" hinzufügen. Intervall und Regenschwellen sind später über *Konfigurieren* änderbar.

Mehrere Zonen: Integration mehrfach mit unterschiedlichen Ventilen einrichten.

## Entwicklung

Dev-Tools werden mit [uv](https://docs.astral.sh/uv/) verwaltet (`pyproject.toml` + `uv.lock`). Die Integration selbst hat keine Python-Abhängigkeiten.

```bash
uv sync            # dev dependencies installieren
uv run ruff check .
uv run pytest
```

Die CI (`.github/workflows/ci.yml`) führt bei jedem PR Ruff, Pytest, einen Syntax-Check des Panels sowie hassfest und die HACS-Validierung aus.

Releases entstehen automatisch (`.github/workflows/release.yml`), sobald ein Push auf `main` etwas unter `custom_components/` oder `hacs.json` ändert: Ist die Version aus `manifest.json` bereits released, erhöht die Action die Patch-Version in `manifest.json`, `pyproject.toml` und `uv.lock` (z.B. `0.10.3` → `0.10.4`), committet das auf `main` und legt das Release an. Wurde die Version im PR manuell erhöht (z.B. `0.11.0`), wird genau diese released. HACS zeigt so die Version statt des Commit-Hashes. Die CI prüft, dass beide Versionen übereinstimmen.

Abhängigkeits-Updates kommen über [Renovate](https://docs.renovatebot.com/) (`renovate.json`): Python-Dev-Tools inkl. `uv.lock` und GitHub Actions. Minor- und Patch-Updates werden bei grüner CI automatisch gemergt, Major-Updates brauchen ein Review.
