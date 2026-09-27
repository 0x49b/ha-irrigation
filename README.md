# Irrigation Scheduler für Home Assistant

Custom Integration für eine automatische Bewässerung einer Zone.

## Features

- **Zeitfenster pro Wochentag**: `von`/`bis` als `time` Entities (Standard 06:00 bis 22:00). Erster Lauf bei `von`, dann alle *n* Stunden (1 bis 24), solange der Start vor `bis` liegt. Beispiel Montag 07:00 bis 22:00, Intervall 6h: 07:00, 13:00, 19:00. Ein Lauf darf über `bis` hinaus dauern. Ist `bis` kleiner oder gleich `von`, geht das Fenster über Mitternacht (z.B. 22:00 bis 04:00); diese Läufe zählen zum Starttag.
- **Dauer pro Wochentag**: 7 `number` Entities (Minuten, `0` = an diesem Tag nicht bewässern). Die Dauer gilt pro Lauf.
- **Regenprüfung**: vor jedem geplanten Lauf wird `weather.get_forecasts` (stündlich, sonst täglich) der gewählten Wetter-Entity abgefragt. Übersprungen wird, wenn im Vorhersagefenster die Regenmenge oder die maximale Regenwahrscheinlichkeit die Schwelle erreicht. Schwelle `0` deaktiviert das jeweilige Kriterium.
- **Ventil**: `switch`, `valve` oder `input_boolean`.
- **Neustart-sicher**: Läuft beim HA-Neustart eine Bewässerung, wird das Ende wiederhergestellt bzw. das Ventil geschlossen, falls das Ende bereits verstrichen ist.

## Sidebar-Panel

Die Integration registriert ein Panel **Bewässerung** in der Sidebar (nur für Admins):

- **Status**: aktueller Zustand, nächster/letzter Lauf, Regenvorhersage, manuell bewässern (Minuten frei wählbar) und stoppen.
- **Einstellungen**: Automatik, Regenprüfung, Ventil, Wetter-Entity, Intervall, Regenschwellen, Vorhersagefenster.
- **Wochenplan**: Montag bis Sonntag mit Dauer, von, bis und Vorschau der Startzeiten.
- **Verlauf**: bewässerte Minuten pro Tag (30 Tage) und Tabelle aller Läufe inkl. übersprungener Läufe mit Regenwerten. Aufbewahrung 90 Tage.

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
| `binary_sensor.*_regen_erwartet` | Würde der nächste Lauf wegen Regen übersprungen |

## Installation

HACS: Repository als *Custom repository* (Typ *Integration*) hinzufügen, oder `custom_components/irrigation_scheduler` nach `<config>/custom_components/` kopieren. Danach HA neu starten und unter *Einstellungen > Geräte & Dienste* "Irrigation Scheduler" hinzufügen. Intervall und Regenschwellen sind später über *Konfigurieren* änderbar.

Mehrere Zonen: Integration mehrfach mit unterschiedlichen Ventilen einrichten.

## Tests

```bash
pip install pytest
pytest tests
```
