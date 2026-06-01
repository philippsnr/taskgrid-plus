# ADR-002: Worker-Auswahlstrategie im Dispatcher

## Kontext

Der Dispatcher empfängt Tasks und muss unter ggf. mehreren verfügbaren Workern eines Typs genau einen auswählen. Die Wahl der Strategie beeinflusst Lastverteilung, Fehlertoleranz und Implementierungskomplexität.

## Entscheidung

**Least Load** — der Worker mit dem niedrigsten gemeldeten `current_load`-Wert wird bevorzugt.

Ablauf in `_select_worker`:

1. Der Dispatcher ruft `LookupWorker` am NameService auf und erhält alle registrierten Worker des gewünschten Typs.
2. Worker, die nicht den Status `ACTIVE` haben (z. B. `UNHEALTHY`, `OFFLINE`), werden herausgefiltert.
3. Ist die verbleibende Menge leer, wird kein Worker zurückgegeben und der Task bleibt in der Queue.
4. Handelt es sich um einen Retry-Versuch, wird der zuletzt fehlgeschlagene Worker ausgeschlossen, sofern mindestens ein anderer Worker verfügbar ist.
5. Aus den verbleibenden Kandidaten wird per `min(candidates, key=lambda w: w.current_load)` der am wenigsten ausgelastete Worker gewählt.

Sonderfälle:
- **Genau ein Worker verfügbar**: wird direkt verwendet (kein Fallback nötig).
- **Alle Worker UNHEALTHY/OFFLINE**: kein Dispatch, Task verbleibt in der Queue; der Dispatcher wartet 1 s und versucht es erneut.

## Alternativen

| Strategie | Bewertung |
|---|---|
| **Round-robin** | Einfach, ignoriert aber unterschiedliche Worker-Kapazitäten (z. B. schnelle vs. langsame VMs). |
| **Random** | Keine Koordination nötig, aber keine Lastberücksichtigung — führt zu ungleichmäßiger Auslastung. |
| **Least Load** *(gewählt)* | Nutzt den bereits im `Worker`-Proto vorhandenen `current_load`-Wert ohne zusätzlichen Zustand im Dispatcher. |
| **Weighted Round-robin** | Berücksichtigt Kapazitäten, erfordert aber persistenten Zähler pro Worker im Dispatcher. |

Least Load wurde gewählt, weil:
- `current_load` bereits Teil des `Worker`-Proto-Messages ist — kein zusätzlicher Koordinationsaufwand.
- Die Strategie unter heterogenen Workern (unterschiedliche CPU/RAM) fairer ist als Round-robin.
- Die Implementierung zustandslos im Dispatcher bleibt (kein persistenter Zähler nötig).

## Konsequenzen

- Tasks werden automatisch zu weniger ausgelasteten Workern gelenkt.
- Bei unverändertem `current_load` (z. B. alle Worker melden 0) verhält sich Least Load wie eine Auswahl des ersten Workers in der Liste — de facto Round-robin-ähnlich, wenn die NameService-Reihenfolge rotiert.
- Die Strategie ist im Log als `strategy="least_loaded"` nachvollziehbar.
- Worker müssen ihren `current_load` korrekt melden; veraltete oder konstant gemeldete Werte reduzieren die Effektivität der Strategie.
