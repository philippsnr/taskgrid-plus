# ADR-001: Retry-Strategie bei Task-Timeout

## Kontext

Der Dispatcher muss erkennen, wenn ein Worker nicht innerhalb eines definierten Timeouts antwortet. In diesem Fall muss entschieden werden, wie mit dem betroffenen Task umgegangen wird: erneute Einplanung, Weiterleitung an einen anderen Worker oder endgültige Markierung als fehlgeschlagen.

## Entscheidung

Es wird eine begrenzte Retry-Strategie mit Worker-Wechsel-Präferenz eingesetzt:

- Der Dispatcher prüft alle 5 Sekunden alle Tasks im Zustand `DISPATCHED` oder `PROCESSING`.
- Überschreitet ein Task den konfigurierten Timeout (`TASK_TIMEOUT_SEC`), wird er in den Zustand `TIMEOUT` versetzt.
- Ist `retry_count < MAX_RETRIES`, wird der Task über `RETRYING` zurück in die Queue gestellt (`QUEUED`) und `retry_count` inkrementiert.
- Bei der erneuten Dispatching-Auswahl wird der zuletzt fehlgeschlagene Worker ausgeschlossen, sofern mindestens ein anderer aktiver Worker verfügbar ist (Least-Load-Selektion unter den verbleibenden Kandidaten).
- Sind keine Retries mehr verfügbar (`retry_count >= MAX_RETRIES`), wird der Task auf `FAILED` gesetzt.

Zustandsübergänge:
```
DISPATCHED/PROCESSING ──(timeout)──► TIMEOUT ──(retry < max)──► RETRYING ──► QUEUED
                                              ──(retry >= max)──► FAILED
```

Konfiguration via Umgebungsvariablen:
- `TASK_TIMEOUT_SEC` (Standard: 60)
- `MAX_RETRIES` (Standard: 3)

## Alternativen

- **Kein Retry, sofort FAILED**: Einfacher, aber unrobust gegenüber transienten Worker-Ausfällen.
- **Unbegrenzte Retries**: Verhindert Task-Verlust, birgt aber das Risiko von Endlosschleifen bei dauerhaft fehlerhaften Payloads.
- **Exponential Backoff vor Re-Enqueue**: Würde die Queue-Last bei vielen gleichzeitigen Timeouts reduzieren, erhöht aber die Komplexität.

## Konsequenzen

- Tasks können nach einem Worker-Ausfall automatisch von einem anderen Worker übernommen werden.
- Die Zustandshistorie (TIMEOUT → RETRYING → QUEUED) ist in den Logs vollständig nachvollziehbar.
- `retry_count` und `last_failed_worker` werden im TaskRecord gespeichert und können für Monitoring ausgewertet werden.
- Bei `MAX_RETRIES=0` wird sofort auf `FAILED` gesetzt — das System ist ohne Code-Änderung konfigurierbar.
