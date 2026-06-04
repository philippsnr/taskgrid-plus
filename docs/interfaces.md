# Schnittstellen- und Protokolldokumentation — TaskGrid+

## 1. Kommunikationsprotokoll

### Warum gRPC?

TaskGrid+ verwendet **gRPC über HTTP/2** als einziges Kommunikationsprotokoll zwischen allen Komponenten. Die Entscheidung ist in [ADR-001](adr/ADR-001.md) ausführlich begründet; zusammengefasst:

| Kriterium | gRPC | Rohes UDP |
|-----------|------|-----------|
| Zustellgarantie | Ja (TCP-basiert) | Nein (Paketverlust möglich) |
| Typsicherheit | Ja (Protobuf-Schema) | Nein (manuell) |
| Code-Generierung | Ja (Stubs aus `.proto`) | Nein |
| Schnittstellendokumentation | Im Schema eingebettet | Manuell |
| Streaming | Bidirektional möglich | Manuell |

### Zuverlässigkeit und Fehlerverhalten

- **Verbindungsaufbau:** gRPC-Kanäle werden lazy initialisiert und gecacht (Worker-Kanäle im Dispatcher, Namensdienst-Stub im Dispatcher und Worker).
- **Timeout-Handling:** Alle kritischen RPC-Aufrufe haben explizite Timeouts (5–10 s). Schlägt ein Aufruf fehl, wird ein `grpc.RpcError` ausgelöst.
- **Retry-Verhalten:** Der Dispatcher re-enqueued Tasks bei nicht erreichbaren Workern (`grpc.RpcError`) oder Ablehnung (`accepted=false`). Details in [ADR-006](adr/ADR-006.md).
- **Fehlerweiterleitung:** Fehler werden nicht als Exceptions an den Client weitergereicht, sondern als strukturierte Antwortfelder (`success=false`, `message`).

### MessageHeader (Nachrichtenumschlag)

Jede Anfrage und Antwort enthält einen `MessageHeader` für Tracing und Korrelation:

```protobuf
message MessageHeader {
  string message_type = 1;  // Name des RPC-Typs
  string request_id   = 2;  // UUID für End-to-End-Tracing
  int64  timestamp    = 3;  // Unix-Epoch in Millisekunden
  string sender       = 4;  // Komponentenname (z.B. "dispatcher")
}
```

**Beispiel (JSON-Darstellung):**
```json
{
  "message_type": "PostTaskRequest",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": 1717200000000,
  "sender": "client"
}
```

---

## 2. Datenstrukturen

### Task

```protobuf
message Task {
  int32      id                   = 1;  // Eindeutige Task-ID (vom Dispatcher vergeben)
  string     type                 = 2;  // Aufgabentyp, z.B. "reverse", "sum"
  string     payload              = 3;  // Eingabedaten als String
  string     result               = 4;  // Ergebnis nach Verarbeitung
  TaskStatus status               = 5;  // Aktueller Zustand
  int64      timestamp_created    = 6;  // Unix-Epoch ms: Zeitpunkt der Erstellung
  int64      timestamp_dispatched = 7;  // Unix-Epoch ms: Zeitpunkt des Dispatches
  int64      timestamp_completed  = 8;  // Unix-Epoch ms: Zeitpunkt des Abschlusses
  int32      retry_count          = 9;  // Anzahl bisheriger Retry-Versuche
  string     assigned_worker      = 10; // worker_id des aktuell zugewiesenen Workers
}
```

### Worker

```protobuf
message Worker {
  string       worker_id      = 1;  // Eindeutige Worker-ID
  string       type           = 2;  // Aufgabentyp, den dieser Worker verarbeitet
  string       address        = 3;  // IP-Adresse / Hostname des Workers
  int32        port           = 4;  // gRPC-Port des Workers
  WorkerStatus status         = 5;  // Aktueller Gesundheitszustand
  int64        last_heartbeat = 6;  // Unix-Epoch ms: letzter empfangener Heartbeat
  int32        current_load   = 7;  // Anzahl aktuell verarbeiteter Tasks
}
```

### TaskStatus-Enum

| Wert | Name | Bedeutung |
|------|------|-----------|
| 0 | `TASK_STATUS_UNSPECIFIED` | Ungültig / unbekannte Task-ID |
| 1 | `CREATED` | Validiert, noch nicht in Queue |
| 2 | `QUEUED` | Wartet in der Dispatcher-Queue |
| 3 | `DISPATCHED` | An Worker gesendet, warte auf Bestätigung |
| 4 | `PROCESSING` | Worker hat angenommen, verarbeitet |
| 5 | `COMPLETED` | Erfolgreich abgeschlossen |
| 6 | `FAILED` | Endgültig fehlgeschlagen |
| 7 | `TIMEOUT` | Kein Ergebnis innerhalb `TASK_TIMEOUT_SEC` |
| 8 | `RETRYING` | Wird erneut eingeplant |

### WorkerStatus-Enum

| Wert | Name | Bedeutung |
|------|------|-----------|
| 0 | `WORKER_STATUS_UNSPECIFIED` | Ungültig |
| 1 | `ACTIVE` | Erreichbar, nimmt Tasks an |
| 2 | `UNHEALTHY` | Kein Heartbeat seit ≥ 30 s — nicht für Dispatch verfügbar |
| 3 | `DRAINING` | Geordneter Shutdown läuft |
| 4 | `OFFLINE` | Kein Heartbeat seit ≥ 90 s — gilt als ausgefallen |

---

## 3. RPC-Dokumentation

### 3.1 DispatcherService (Port 50051)

#### `PostTask` — Client → Dispatcher

Stellt einen neuen Task in die Queue.

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | Korrelations-ID, Absender |
| `type` | string | Aufgabentyp (z.B. `"reverse"`) — darf nicht leer sein |
| `payload` | string | Eingabedaten — darf nicht leer sein |

**Response:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `success` | bool | `true` = Task eingereiht |
| `task_id` | int32 | Vergebene Task-ID (nur wenn `success=true`) |
| `message` | string | Fehlerbeschreibung (nur wenn `success=false`) |

**Fehlerfälle:**
- `type` oder `payload` leer → `success=false`
- Kein Worker für den angegebenen Typ registriert → `success=false`

---

#### `GetResult` — Client → Dispatcher

Fragt Status und Ergebnis eines Tasks ab.

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `task_id` | int32 | ID des abzufragenden Tasks |

**Response:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `success` | bool | `false` wenn Task-ID unbekannt |
| `task_id` | int32 | |
| `result` | string | Ergebnis (nur wenn `COMPLETED`) |
| `status` | TaskStatus | Aktueller Task-Zustand |
| `message` | string | Fehlerbeschreibung (bei `FAILED`/`TIMEOUT`) |

**Fehlerfälle:**
- Unbekannte `task_id` → `success=false`, `status=TASK_STATUS_UNSPECIFIED`

---

#### `ReturnResult` — Worker → Dispatcher

Worker liefert das Verarbeitungsergebnis zurück.

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `task_id` | int32 | ID des abgeschlossenen Tasks |
| `result` | string | Ergebnis-Payload |
| `worker_id` | string | ID des Senders |
| `success` | bool | `false` wenn Verarbeitungsfehler aufgetreten |
| `error_message` | string | Fehlerbeschreibung (nur wenn `success=false`) |

**Response:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `success` | bool | |
| `message` | string | Fehlerbeschreibung |

**Fehlerfälle:**
- Unbekannte `task_id` → abgelehnt
- Task nicht in Zustand `DISPATCHED`/`PROCESSING` (z.B. bereits `COMPLETED`) → abgelehnt (Duplikat-Schutz)
- `worker_id` stimmt nicht mit zugewiesenem Worker überein → abgelehnt

---

#### `GetDispatcherStatus` — Monitoring → Dispatcher

Liefert aktuelle Systemmetriken des Dispatchers.

**Request:** nur `header`

**Response:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `workers_registered` | int32 | Bekannte Worker-Adressen im Channel-Cache |
| `workers_active` | int32 | Aktive Worker laut Namensdienst |
| `supported_task_types` | repeated string | Verfügbare Aufgabentypen |
| `tasks_queued` | int32 | Tasks aktuell in Queue |
| `tasks_running` | int32 | Tasks in `DISPATCHED`/`PROCESSING` |
| `tasks_completed` | int32 | Abgeschlossene Tasks |
| `tasks_failed` | int32 | Fehlgeschlagene Tasks |
| `avg_processing_time_ms` | double | Ø Verarbeitungsdauer in ms |
| `total_timeouts` | int32 | Gesamtanzahl Timeouts |
| `total_retries` | int32 | Gesamtanzahl Retries |

---

### 3.2 NameService (Port 50052)

#### `RegisterWorker` — Worker → Namensdienst

Worker meldet sich beim Start an.

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `worker_id` | string | Eindeutige Worker-ID |
| `type` | string | Aufgabentyp des Workers |
| `address` | string | Erreichbare IP / Hostname |
| `port` | int32 | gRPC-Port des Workers |
| `capacity` | int32 | Maximale parallele Tasks (optional) |

**Response:** `success`, `message`

**Verhalten:** Worker versucht die Registrierung mit Exponential-Backoff-Retry (bis zu 10 Versuche, max. 30 s Wartezeit).

---

#### `Heartbeat` — Worker → Namensdienst

Worker signalisiert Verfügbarkeit periodisch (Standard: alle 10 s).

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `worker_id` | string | |
| `timestamp` | int64 | Unix-Epoch ms |
| `current_load` | int32 | Anzahl aktuell verarbeiteter Tasks |

**Response:** `success`, `message`

**Fehlerfälle:**
- Unbekannter `worker_id` (z.B. Namensdienst neu gestartet) → `success=false`; Worker versucht Re-Registrierung.

---

#### `LookupWorker` — Dispatcher → Namensdienst

Dispatcher fragt aktive Worker für einen bestimmten Typ ab.

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `type` | string | Gesuchter Aufgabentyp |

**Response:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `success` | bool | |
| `workers` | repeated Worker | Alle `ACTIVE` Worker des Typs |
| `message` | string | |

---

#### `DeregisterWorker` — Worker → Namensdienst

Worker meldet sich beim Shutdown explizit ab.

**Request:** `header`, `worker_id`

**Response:** `success`, `message`

**Verhalten:** Wird bei SIGTERM/SIGINT ausgelöst; Worker wechselt intern in den Zustand `DRAINING`.

---

#### `GetNameServiceStatus` — Monitoring → Namensdienst

**Response:** analog zu `GetDispatcherStatus` (workers_registered, workers_active, supported_task_types, …)

---

### 3.3 WorkerService (Port 50053 pro Container)

#### `ProcessTask` — Dispatcher → Worker

Dispatcher übergibt einen Task zur Verarbeitung.

**Request:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `task` | Task | Vollständiges Task-Objekt inkl. Payload |

**Response:**

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `header` | MessageHeader | |
| `accepted` | bool | `true` = Worker nimmt Task an und verarbeitet ihn im Hintergrund |
| `message` | string | Ablehnungsgrund (wenn `accepted=false`) |

**Verhalten:** Der Worker antwortet sofort (nicht-blockierend). Die Verarbeitung läuft in einem Hintergrund-Thread. Das Ergebnis wird anschließend via `ReturnResult` an den Dispatcher gesendet.

**Fehlerfälle:**
- Worker am Kapazitätslimit (`current_load >= capacity`) → `accepted=false`
- Worker im Shutdown (`stop_event` gesetzt) → `accepted=false`

---

## 4. Port-Übersicht

| Komponente | Port (intern) | Port (extern/Host) | Konfiguration |
|------------|--------------|-------------------|---------------|
| Dispatcher | 50051 | 50051 | `DISPATCHER_PORT` |
| Namensdienst | 50052 | 50052 | `NAMESERVICE_PORT` |
| Worker (je Instanz) | 50053 | — (kein Host-Mapping) | `WORKER_PORT` |
| Monitoring | — | — | (nur ausgehend) |
| Client | — | — | (nur ausgehend) |

Worker sind nur innerhalb des Docker-Netzwerks erreichbar — kein direkter Zugriff von außen vorgesehen.

---

## 5. Erweiterbarkeit — Neuen Aufgabentyp hinzufügen

Dank der Trennung zwischen Dispatcher (Koordination) und Worker (Fachlogik) sind **keine Änderungen am Dispatcher, Namensdienst oder Client** erforderlich, um einen neuen Aufgabentyp zu ergänzen.

### Schritt 1: Handler implementieren

In `worker/handlers.py` eine neue Funktion hinzufügen:

```python
def handle_mytype(payload: str) -> tuple[bool, str]:
    try:
        result = do_something(payload)
        return True, result
    except Exception as e:
        return False, f"Error: {str(e)}"
```

### Schritt 2: Handler registrieren

```python
HANDLERS = {
    "reverse": handle_reverse,
    "sum":     handle_sum,
    # ...
    "mytype":  handle_mytype,  # ← hier eintragen
}
```

### Schritt 3: Worker-Container starten

```bash
# Direkt:
WORKER_ID=worker-mytype-1 WORKER_TYPE=mytype python worker/main.py

# Via Docker Compose:
docker compose up --scale worker-mytype=2
```
