# Task-Zustandsmodell — TaskGrid+

## 1. Zustandsdiagramm

```
                          ┌─────────────────────────────────────────────────────────┐
                          │                    Dispatcher                           │
                          │                                                         │
   Client.PostTask()      │                                                         │
        │                 │                                                         │
        ▼                 │                                                         │
    [CREATED]─────────────────────────────────────────────────────────────────────► │
        │  (Validierung ok)                                                         │
        ▼                 │                                                         │
    [QUEUED] ◄────────────────── RETRYING ◄───────────────────────────────────────  │
        │  (Dispatch-Loop             │                                             │
        │   wählt Worker)             │                                             │
        ▼                 │           │                                             │
   [DISPATCHED]           │       [TIMEOUT] ◄─── Timeout-Checker (alle 5s)          │
        │  (Worker nimmt             │    retry_count <             retry_count >=  │
        │   Task an)      │          │    MAX_RETRIES               MAX_RETRIES     │
        ▼                 │          │                                   │          │
   [PROCESSING]           │          │                               [FAILED]       │
        │  (Worker meldet            └───────────────────────────────────┘          │
        │   Ergebnis)     │                                                         │
        ├──(success=true)─────────────────────────────────────────────────────────► │
        │                 │   [COMPLETED]                                           │
        └──(success=false)────────────────────────────────────────────────────────► │
                          │   [FAILED]                                              │
                          │                                                         │
                          │  Sonderfälle (kein Worker verfügbar):                   │
                          │  [QUEUED] ──(kein Worker, retry_count > 0)──► [FAILED]  │
                          └─────────────────────────────────────────────────────────┘
```

### Vereinfachte Zustandsübergänge

```
CREATED ──► QUEUED ──► DISPATCHED ──► PROCESSING ──► COMPLETED
                                          │
                                          ├──► FAILED   (Worker meldet Fehler)
                                          │
                                          └──► TIMEOUT ──┬──► RETRYING ──► QUEUED   (retry < MAX)
                                                         └──► FAILED               (retry ≥ MAX)

QUEUED ──► FAILED   (kein alternativer Worker bei Retry)
```

---

## 2. Beschreibung aller 8 Zustände

| # | Status | Beschreibung |
|---|--------|-------------|
| 0 | `TASK_STATUS_UNSPECIFIED` | Ungültiger/unbekannter Status — wird nur beim Lookup einer unbekannten `task_id` zurückgegeben |
| 1 | `CREATED` | Task wurde validiert und vom Dispatcher entgegengenommen; wird unmittelbar in `QUEUED` überführt (kein persistenter Zwischenzustand in der Queue) |
| 2 | `QUEUED` | Task wartet in der In-Memory-FIFO-Queue auf Dispatch; auch Zielzustand nach einem Retry |
| 3 | `DISPATCHED` | Dispatcher hat dem Worker eine `ProcessTask`-Anfrage geschickt; wartet auf Bestätigung (`accepted`) |
| 4 | `PROCESSING` | Worker hat den Task angenommen (`accepted=true`); Verarbeitung läuft im Worker-Thread |
| 5 | `COMPLETED` | Worker hat `ReturnResult` mit `success=true` zurückgesendet; Ergebnis ist abrufbar |
| 6 | `FAILED` | Task endgültig fehlgeschlagen — entweder Worker-Fehler (`success=false`), Timeout nach Ausschöpfung aller Retries, kein alternativer Worker verfügbar oder ungültiger Typ/Payload |
| 7 | `TIMEOUT` | Dispatcher hat keinen `ReturnResult`-Aufruf innerhalb von `TASK_TIMEOUT_SEC` erhalten; kurzlebiger Zwischenzustand vor `RETRYING` oder `FAILED` |
| 8 | `RETRYING` | Task wird erneut eingeplant; kurzlebiger Zwischenzustand — `retry_count` wird inkrementiert, `last_failed_worker` gesetzt, danach sofort `QUEUED` |

---

## 3. Übergangstabelle (State × Event → Neuer Status)

| Ausgangszustand | Ereignis / Bedingung | Auslösende Komponente | Neuer Status |
|-----------------|---------------------|----------------------|-------------|
| — | `PostTask` empfangen, Validierung ok | Dispatcher (`post_task`) | `CREATED` |
| `CREATED` | Task in Store gespeichert und in Queue eingereiht | Dispatcher (`post_task`) | `QUEUED` |
| `QUEUED` | Dispatch-Loop wählt Worker aus, sendet `ProcessTask` | Dispatcher (`_dispatch_to_worker`) | `DISPATCHED` |
| `QUEUED` | Kein Worker verfügbar, `retry_count > 0` (Retry ohne Alternative) | Dispatcher (`_dispatch_loop`) | `FAILED` |
| `QUEUED` | Kein Worker verfügbar, `retry_count == 0` (Erstversuch) | Dispatcher (`_dispatch_loop`) | `QUEUED` (re-enqueue, kurzes Backoff) |
| `DISPATCHED` | Worker antwortet mit `accepted=true` | Dispatcher (`_dispatch_to_worker`) | `PROCESSING` |
| `DISPATCHED` | Worker antwortet mit `accepted=false` (Kapazität voll) | Dispatcher (`_dispatch_to_worker`) | `QUEUED` (re-enqueue) |
| `DISPATCHED` | Worker nicht erreichbar (gRPC-Fehler) | Dispatcher (`_dispatch_to_worker`) | `QUEUED` (re-enqueue) |
| `DISPATCHED` | Elapsed > `TASK_TIMEOUT_SEC` | Dispatcher (`_timeout_loop`, alle 5s) | `TIMEOUT` |
| `PROCESSING` | Worker sendet `ReturnResult` mit `success=true` | Dispatcher (`return_result`) | `COMPLETED` |
| `PROCESSING` | Worker sendet `ReturnResult` mit `success=false` | Dispatcher (`return_result`) | `FAILED` |
| `PROCESSING` | Elapsed > `TASK_TIMEOUT_SEC` | Dispatcher (`_timeout_loop`, alle 5s) | `TIMEOUT` |
| `TIMEOUT` | `retry_count < MAX_RETRIES` | Dispatcher (`_timeout_loop`) | `RETRYING` |
| `TIMEOUT` | `retry_count >= MAX_RETRIES` | Dispatcher (`_timeout_loop`) | `FAILED` |
| `RETRYING` | `retry_count` inkrementiert, `last_failed_worker` gesetzt | Dispatcher (`_timeout_loop`) | `QUEUED` |
| `COMPLETED` | — | — | (Terminalzustand) |
| `FAILED` | — | — | (Terminalzustand) |

---

## 4. Verhinderung ungültiger Zustandsübergänge

Der Dispatcher implementiert explizite Guards, die ungültige Zustandsübergänge abweisen:

### Doppelte Ergebnisse (Duplicate Results)

`ReturnResult` wird nur verarbeitet, wenn der Task im Zustand `DISPATCHED` oder `PROCESSING` ist:

```python
if task.status not in (taskgrid_pb2.DISPATCHED, taskgrid_pb2.PROCESSING):
    if task.status == taskgrid_pb2.COMPLETED:
        # Doppeltes Ergebnis — ignorieren, Warnung loggen
        return ReturnResultResponse(success=False, message="task already completed")
    else:
        # Veralteter Zustand (z. B. FAILED nach Timeout) — ignorieren
        return ReturnResultResponse(success=False, message="task not in active state")
```

**Praktischer Fall:** Worker verarbeitet einen Task, der zwischenzeitlich vom Timeout-Checker auf `FAILED` gesetzt wurde. Das verspätete `ReturnResult` des Workers wird stillschweigend verworfen.

### Falsche Worker-Zuordnung (Wrong Worker)

Wenn ein `ReturnResult` von einem anderen Worker als dem zugewiesenen eintrifft, wird es abgelehnt:

```python
if task.assigned_worker and worker_id != task.assigned_worker:
    return ReturnResultResponse(success=False, message="task assigned to different worker")
```

### Validierung vor Task-Erstellung

Bei `PostTask` wird geprüft, ob `type` und `payload` nicht leer sind. Ist kein Worker für den angegebenen Typ beim Namensdienst registriert, wird der Task gar nicht erst erstellt (`success=false`, kein Zustandsübergang).

---

## 5. Timeout- und Retry-Verhalten

### Timeout-Erkennung

Ein Hintergrund-Thread (`timeout-checker`) prüft alle **5 Sekunden** alle Tasks im Zustand `DISPATCHED` oder `PROCESSING`:

```
elapsed_ms = now_ms - task.timestamp_dispatched
if elapsed_ms > TASK_TIMEOUT_SEC * 1000:
    → TIMEOUT
```

Konfiguration via Umgebungsvariable `TASK_TIMEOUT_SEC` (Standard: **60 Sekunden**).

### Retry-Ablauf

```
TIMEOUT erkannt
    │
    ├── retry_count < MAX_RETRIES
    │       ├── retry_count += 1
    │       ├── last_failed_worker = timed_out_worker
    │       ├── assigned_worker = ""
    │       ├── timestamp_dispatched = 0
    │       ├── Status: RETRYING
    │       └── Status: QUEUED   →   Task erneut einreihen
    │
    └── retry_count >= MAX_RETRIES
            └── Status: FAILED
                error_message = "task timed out after maximum retries"
```

Konfiguration via Umgebungsvariable `MAX_RETRIES` (Standard: **3**).

### Worker-Ausschluss bei Retry

Der Dispatcher schließt bei der Worker-Auswahl nach einem Timeout den zuletzt fehlgeschlagenen Worker aus (`last_failed_worker`). Falls nur ein Worker verfügbar ist, fällt er auf diesen zurück. Falls kein alternativer Worker gefunden wird und `retry_count > 0`, wird der Task sofort auf `FAILED` gesetzt.

### Neueinplanung (Re-Scheduling)

Tasks werden in folgenden Fällen zurück in die Queue gestellt (ohne Retry-Zähler zu erhöhen):

| Ursache | Bedingung |
|---------|-----------|
| Worker lehnt ab (`accepted=false`) | Kapazitätsgrenze erreicht |
| Worker nicht erreichbar (gRPC-Fehler) | Netzwerkfehler beim `ProcessTask`-Aufruf |
| Namensdienst temporär nicht verfügbar | `LookupWorker`-RPC schlägt fehl |
| Kein Worker registriert (Erstversuch) | `retry_count == 0`, kurzes Backoff (1s) |
