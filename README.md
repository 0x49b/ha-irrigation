# Irrigation Scheduler für Home Assistant

Custom Integration für eine automatische Bewässerung einer Zone.

## Features

- **Fester Scheduler**: ab einer Startzeit alle *n* Stunden (1 bis 24). Der Zyklus wird täglich an der Startzeit neu verankert, z.B. Start 06:00, Intervall 12h: 06:00 und 18:00.
- **Dauer pro Wochentag**: 7 `number` Entities (Minuten, `0` = an diesem Tag nicht bewässern). Die Dauer gilt pro Lauf.
- **Regenprüfung**: vor jedem geplanten Lauf wird `weather.get_forecasts` (stündlich, sonst täglich) der gewählten Wetter-Entity abgefragt. Übersprungen wird, wenn im Vorhersagefenster die Regenmenge oder die maximale Regenwahrscheinlichkeit die Schwelle erreicht. Schwelle `0` deaktiviert das jeweilige Kriterium.
- **Ventil**: `switch`, `valve` oder `input_boolean`.
- **Neustart-sicher**: Läuft beim HA-Neustart eine Bewässerung, wird das Ende wiederhergestellt bzw. das Ventil geschlossen, falls das Ende bereits verstrichen ist.

## Entities

| Entity | Beschreibung |
| --- | --- |
| `switch.*_automatik` | Automatischer Scheduler an/aus |
| `switch.*_regenprufung` | Regenprüfung für geplante Läufe an/aus |
| `switch.*_bewasserung` | Manuell starten (Dauer des heutigen Tages, ohne Regenprüfung) / stoppen |
| `number.*_dauer_<tag>` | Dauer pro Wochentag in Minuten |
| `sensor.*_status` | `idle`, `watering`, `skipped_rain`, `skipped_no_duration`, `error` |
| `sensor.*_nachster_lauf` / `_letzter_lauf` | Zeitstempel |
| `sensor.*_dauer_nachster_lauf` | Dauer des nächsten Laufs |
| `sensor.*_regenvorhersage` / `_regenwahrscheinlichkeit` | Summe mm / max. % im Vorhersagefenster (alle 30 min aktualisiert) |
| `binary_sensor.*_regen_erwartet` | Würde der nächste Lauf wegen Regen übersprungen |

## Installation

HACS: Repository als *Custom repository* (Typ *Integration*) hinzufügen, oder `custom_components/irrigation_scheduler` nach `<config>/custom_components/` kopieren. Danach HA neu starten und unter *Einstellungen > Geräte & Dienste* "Irrigation Scheduler" hinzufügen. Startzeit, Intervall und Regenschwellen sind später über *Konfigurieren* änderbar.

Mehrere Zonen: Integration mehrfach mit unterschiedlichen Ventilen einrichten.

## Tests

```bash
pip install pytest
pytest tests
```
