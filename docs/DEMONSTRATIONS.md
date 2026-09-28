# Fünf Videos, die echte Funktionen zeigen

## Neue Folge ab 0.5: „Drei KI-Regisseure, ein Gewinner“

Aus demselben Szenenprojekt werden drei editierbare Stilrichtungen angelegt: ruhig, verspielt, dramatisch. Zunächst nur die Bildvorschauen erzeugen. In der Vergleichsseite pro Szene eine Richtung wählen, die Auswahl exportieren und mit `project compose --dry-run` den Aufwand für den Gewinner ansehen. Erst dessen fehlende Stufen produzieren. Task-IDs und Prüfsummen belegen die Wiederverwendung. Die drei Richtungen sind editierbare Regie-Briefs, keine automatisch gestarteten separaten KI-Agenten.

Diese Rezepte sind Aufnahmeideen, keine Behauptung bereits produzierter KIE-Ergebnisse. Vor einer Veröffentlichung die verwendeten Modelle und Resultate live prüfen. Lokale Testclips beweisen Schnitt und Wiederaufnahme, nicht die Qualität eines generativen Modells.

## 1. „Ich ändere nur Szene 2 – der Rest bleibt erhalten“

**Aufhänger:** Ein fertiger Clip gefällt fast, nur eine Kamerafahrt ist falsch. Zeige zuerst das Problem, dann die gezielte Korrektur.

**Beleg:** `project edit ... scene-2 --motion "Slow orbit" --dry-run --json` nennt nur `scene-2.video` und `assembly`. Danach anwenden, mit `--phase videos --max-jobs 1` produzieren, den neuen Clip prüfen und neu rendern. Vorher/Nachher-Receipts zeigen unveränderte Task-IDs und Hashes für andere Szenen.

**Nicht behaupten:** Dass die neue Generation pixelgenau vorhersehbar ist oder dass kein anderer Anbieter selektive Änderungen kennt.

## 2. „Ein Produktfoto wird zum zusammenhängenden Spot“

**Ablauf:** Projekt anlegen; Produkt als Entity importieren; den drei Szenen zuordnen; Szenenkarten und Sprechertext zeigen. Erst Bilder erzeugen und prüfen, dann animieren, Sprache und Musik ergänzen, montieren.

**Beleg:** `project storyboard` zeigt Karten und Resultate. `project report` zeigt Jobs, Reviews, bekannte Kosten und fehlende Kostenbeobachtungen. Verpackung, Logo, Geometrie und gesprochene Behauptungen tatsächlich prüfen.

**Nicht behaupten:** Dass Referenzbilder Identitätstraining ersetzen oder Kontinuität garantieren.

## 3. „Mein Agent kann während der Produktion abstürzen“

**Ablauf:** Zuerst die kostenlose Regression mit simuliertem verlorenen Submit zeigen. Für eine echte Produktion nur einen bereits dokumentierten Task unterbrechen und wiederaufnehmen; keine künstlichen zusätzlichen bezahlten Jobs für den Effekt bestellen.

**Beleg:** Bekannte Task-ID wird erneut abgefragt, nicht neu angelegt. Unbekannter Ausgang führt zu `needs_recovery`. Die Anzahl der Create-Aufrufe im Test bleibt eins.

**Nicht behaupten:** Eine Exactly-once-Garantie für das KIE-Backend. Die Funktion verhindert blindes Wiederholen und erhält Belege.

## 4. „Agent A plant – Agent B macht weiter“

**Ablauf:** Projekt und freigegebene Assets mit `project export` als ZIP packen. In einem anderen Ordner oder auf einem anderen Host öffnen, `project plan` und `project report` ausführen und gezielt weiterarbeiten.

**Beleg:** Dateien, Hashes, Szenenplan und Reviews sind vorhanden; der ursprüngliche Chat wird nicht gebraucht. Vor der Übergabe müssen aktive oder unklare Jobs geklärt sein.

**Nicht behaupten:** Dass zwei getrennte Kopien gleichzeitig durch eine verteilte Sperre geschützt wären. Eine aktive Produktionskopie verwenden.

## 5. „Neue KIE-Modelle ohne jedes Mal den Skill umzubauen“

**Ablauf:** `models --live`, `model NAME --json` und einen begrenzten `catalog audit --limit 10` zeigen. Dann eine Audiooperation, einen promptlosen Transform und einen KIE-LLM-Vertrag erklären.

**Beleg:** Familien, verschachtelte Eingaben, Schema-Hash und Grenzen sind sichtbar. Sprachmodelle können Skriptideen liefern; ihre Ausgaben werden nicht als Shell-Kommandos ausgeführt.

**Nicht behaupten:** Dass jede Dokumentationsseite ein Modell ist oder dass ein validiertes Schema eine erfolgreiche Generierung beweist.

## Weitere mögliche Experimente

- Mit denselben drei Szenen mehrere Modelle anhand von Nutzbarkeit, Zeit und tatsächlichen Kosten vergleichen. Erst danach automatisches Qualitätsrouting entwickeln.
- Ein kleines lokales Bewertungsprofil aus angenommenen/abgelehnten Ergebnissen entwickeln. Das ist noch keine Funktion dieser Version.
- Visuelle Kontinuitätsprüfung durch ein geeignetes multimodales Modell ergänzen. Diese Version speichert menschliche/Host-Agent-Reviews und technische Medienchecks; sie enthält keinen eigenständigen Vision-Judge.

Ein sinnvoller erster Live-Test umfasst drei Bilder, drei kurze Clips, optional drei Sprachaufträge und einen Musikauftrag. Die konkreten Modelle, Parameter und das Job-Limit vorher im Plan ansehen. Ein Job-Limit ist keine garantierte Euro-Obergrenze.
