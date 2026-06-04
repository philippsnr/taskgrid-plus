# Architekturdokumentation — TaskGrid+

## 1. Architekturdiagramm

Das folgende Diagramm zeigt alle fünf Komponenten des Systems und ihre Kommunikationsbeziehungen. Alle Verbindungen verwenden gRPC über Protocol Buffers.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              Docker-Netzwerk                               │
│                                                                            │
│                PostTask / GetResult            LookupWorker                │
│   ┌──────────┐                ┌─────────────┐             ┌─────────────┐  │
│   │  Client  │◄──────────────►│ Dispatcher  │────────────►│Namensdienst │  │
│   └──────────┘                └─────────────┘             └─────────────┘  │
│                                      │  ProcessTask / Register / ▲         │
│                                      │  ReturnResult  Heartbeat  │         │
│                                      │                           │         │
│                                      ▼                           │         │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │  Worker-Pool (skalierbar, ein Container pro Aufgabentyp)           │   │
│   │   ┌────────────┐    ┌────────────┐    ┌────────────┐               │   │
│   │   │  reverse   │    │    sum     │    │    hash    │   ...         │   │
│   │   └────────────┘    └────────────┘    └────────────┘               │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│                                                                            │
│                    GetDispatcherStatus / GetNameServiceStatus              │
│   ┌────────────┐                                                           │
│   │ Monitoring │ ──────────────────────────────────────────────────────►   │
│   └────────────┘                                                           │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Vereinfachte Übersicht der Kommunikationsflüsse

```
Client ──PostTask──► Dispatcher ──LookupWorker──► Namensdienst
                         │                              ▲
                         │ ProcessTask                  │ Register / Heartbeat
                         ▼                              │
                       Worker ──────────────────────────┘
                         │
                         │ ReturnResult
                         ▼
                     Dispatcher ──GetResult──► Client

Monitoring ──GetDispatcherStatus───► Dispatcher
Monitoring ──GetNameServiceStatus──► Namensdienst
```

---

## 2. Architekturbegründung

### Gewählte Komponentenstruktur

Das System ist als lose gekoppelter Verbund eigenständiger Prozesse (Microservices) konzipiert. Jede Komponente läuft in einem eigenen Docker-Container und kommuniziert ausschließlich über gRPC. Diese Entscheidung wurde aus mehreren verteilten-Systeme-Prinzipien abgeleitet:

#### Verteilungstransparenz (Distribution Transparency)

Aus Sicht des Clients ist es irrelevant, auf welchem Host oder in welchem Container der Dispatcher läuft. Die gRPC-Schnittstelle abstrahiert den physischen Ort vollständig. Dasselbe gilt für den Dispatcher beim Zugriff auf Worker: Über den Namensdienst wird ein Worker per Adresse/Port referenziert — der Dispatcher muss nicht wissen, wie viele Worker-Instanzen existieren oder wo sie physisch laufen.

#### Fehlertransparenz (Failure Transparency)

Der Dispatcher behandelt Worker-Ausfälle transparent gegenüber dem Client: Überschreitet ein Task den konfigurierten Timeout, wird er automatisch erneut eingeplant (`RETRYING`) und einem anderen Worker zugewiesen. Der Client erhält erst dann eine endgültige Antwort, wenn der Task entweder abgeschlossen (`COMPLETED`) oder definitiv fehlgeschlagen (`FAILED`) ist.

#### Skalierungstransparenz (Replication Transparency)

Worker können horizontal skaliert werden (`docker compose up --scale worker-sum=3`). Der Namensdienst verwaltet alle registrierten Instanzen, und der Dispatcher wählt per Least-Load-Strategie den am wenigsten ausgelasteten Worker aus. Diese Skalierung ist für den Client vollkommen transparent.

#### Separation of Concerns

| Komponente     | Verantwortung |
|----------------|---------------|
| Client         | Aufgaben stellen, Ergebnisse abfragen |
| Dispatcher     | Koordination, Queue-Management, Retry-Logik |
| Namensdienst   | Service Discovery, Worker-Gesundheit |
| Worker         | Fachliche Aufgabenverarbeitung |
| Monitoring     | Beobachtbarkeit (Read-only) |

Der Dispatcher enthält bewusst keine fachliche Logik — er koordiniert nur. Worker enthalten keine Koordinationslogik — sie verarbeiten nur. Dies ermöglicht das unabhängige Austauschen, Erweitern und Skalieren beider Seiten.

#### Entkopplung durch Namensdienst

Der Dispatcher kennt Worker-Adressen nicht zur Deployment-Zeit. Stattdessen registrieren sich Worker beim Start beim Namensdienst und kündigen sich bei Shutdown explizit ab. Der Dispatcher fragt den Namensdienst unmittelbar vor der Dispatch-Entscheidung ab (`LookupWorker`). Das System ist dadurch robust gegenüber Worker-Neustarts und dynamischen Skalierungsoperationen.

---

## 3. Komponentenbeschreibungen

### 3.1 Client

**Verantwortung:**
Stellt Aufgaben an den Dispatcher und fragt Ergebnisse ab. Fungiert als Systemeingang für Endnutzer oder externe Systeme.

**Exponierte Schnittstellen:** keine (rein aufrufend)

**Konsumierte Schnittstellen:**
- `DispatcherService.PostTask` — sendet eine neue Aufgabe (Typ + Payload)
- `DispatcherService.GetResult` — fragt den aktuellen Status und das Ergebnis einer Aufgabe per `task_id` ab

**Gehaltener Zustand:** Die `task_id`, die nach `PostTask` zurückgegeben wird, wird im Prozessspeicher gehalten und für den `GetResult`-Aufruf verwendet. Der Client ist zustandslos über Sitzungen hinaus.

---

### 3.2 Dispatcher

**Verantwortung:**
Zentrale Koordinationskomponente. Nimmt Aufgaben entgegen, verwaltet die Task-Queue, verteilt Aufgaben an geeignete Worker und überwacht deren Bearbeitung (Timeout, Retry).

**Exponierte Schnittstellen:**
- `DispatcherService.PostTask` — empfängt neue Aufgaben vom Client
- `DispatcherService.GetResult` — liefert Task-Status und -Ergebnis an den Client
- `DispatcherService.ReturnResult` — empfängt Ergebnisse von Workern
- `DispatcherService.GetDispatcherStatus` — liefert Systemmetriken an Monitoring

**Konsumierte Schnittstellen:**
- `NameService.LookupWorker` — fragt aktive Worker für einen Aufgabentyp ab
- `WorkerService.ProcessTask` — übergibt eine Aufgabe an einen Worker

**Gehaltener Zustand:**
- `TaskStore`: In-Memory-Dictionary (`task_id → TaskRecord`), enthält alle Tasks mit Status, Payload, Ergebnis, Timestamps, Retry-Zähler und zugewiesenem Worker
- `TaskQueue`: Thread-sichere FIFO-Queue mit `task_id`s wartender Tasks
- Monitoring-Zähler: Gesamtanzahl Timeouts, Summe Verarbeitungszeiten, Anzahl abgeschlossener Tasks
- Namensdienst-Stub: gecachter gRPC-Kanal
- Worker-Channels: Dictionary gecachter gRPC-Kanäle zu Workern (`worker_id → grpc.Channel`)

---

### 3.3 Namensdienst

**Verantwortung:**
Service-Discovery-Komponente. Verwaltet die Registrierung aktiver Worker, empfängt Heartbeats und meldet inaktive Worker automatisch ab. Ermöglicht dem Dispatcher, passende Worker für einen Aufgabentyp zu finden.

**Exponierte Schnittstellen:**
- `NameService.RegisterWorker` — Worker registriert sich beim Start
- `NameService.Heartbeat` — Worker meldet sich periodisch mit aktuellem Load
- `NameService.DeregisterWorker` — Worker meldet sich beim Shutdown ab
- `NameService.LookupWorker` — Dispatcher fragt aktive Worker für einen Typ ab
- `NameService.GetNameServiceStatus` — liefert Systemmetriken an Monitoring

**Konsumierte Schnittstellen:** keine

**Gehaltener Zustand:**
- `_registry`: In-Memory-Dictionary (`worker_id → Worker`), enthält für jeden registrierten Worker: `worker_id`, `type`, `address`, `port`, `status` (ACTIVE / UNHEALTHY / DRAINING / OFFLINE), `last_heartbeat`, `current_load`
- Hintergrund-Thread (`health-checker`): prüft sekündlich alle Worker und demoviert sie bei ausbleibendem Heartbeat (`ACTIVE → UNHEALTHY → OFFLINE`)

---

### 3.4 Worker

**Verantwortung:**
Spezialisierte Verarbeitungseinheit für einen bestimmten Aufgabentyp (z. B. `reverse`, `sum`, `hash`). Registriert sich beim Start beim Namensdienst, empfängt Aufgaben vom Dispatcher, verarbeitet sie asynchron und sendet das Ergebnis zurück.

**Exponierte Schnittstellen:**
- `WorkerService.ProcessTask` — empfängt Aufgaben vom Dispatcher; antwortet sofort mit `accepted=true/false`, verarbeitet die Aufgabe in einem Hintergrund-Thread

**Konsumierte Schnittstellen:**
- `NameService.RegisterWorker` — beim Start (mit Exponential-Backoff-Retry)
- `NameService.Heartbeat` — periodisch (Standard: alle 10 Sekunden) mit aktuellem Load
- `NameService.DeregisterWorker` — beim Shutdown (SIGTERM/SIGINT)
- `DispatcherService.ReturnResult` — nach Abschluss einer Aufgabe

**Gehaltener Zustand:**
- `_current_load`: Anzahl aktuell laufender Task-Threads (thread-safe, via Lock)
- `_task_threads`: Dictionary (`task_id → Thread`) laufender Verarbeitungs-Threads
- gRPC-Stubs (gecacht): je ein Kanal zum Namensdienst und zum Dispatcher

**Aufgabentypen (implementiert):**

| Typ        | Verarbeitung |
|------------|-------------|
| `reverse`  | Payload-String umkehren |
| `sum`      | Zahlen (kommagetrennt) summieren |
| `hash`     | SHA256-Hashwert berechnen |
| `upper`    | Großschreibung |
| `wait`     | Verzögerung in Sekunden simulieren |
| `wordcount`| Wörter zählen |
| `lower`    | Kleinschreibung |
| `base64`   | Base64-Kodierung |
| `prime`    | Primzahlprüfung |

---

### 3.5 Monitoring

**Verantwortung:**
Reine Beobachtungskomponente. Fragt regelmäßig den Dispatcher und den Namensdienst nach Systemmetriken ab und gibt diese aus. Hat keinen Einfluss auf den Verarbeitungsablauf.

**Exponierte Schnittstellen:** keine

**Konsumierte Schnittstellen:**
- `DispatcherService.GetDispatcherStatus` — Anzahl Tasks (queued, running, completed, failed), Timeouts, Retries, durchschnittliche Verarbeitungszeit
- `NameService.GetNameServiceStatus` — Anzahl registrierter und aktiver Worker, unterstützte Aufgabentypen

**Gehaltener Zustand:** keiner (zustandslos, poll-basiert)

---

## 4. Ablaufdiagramme

### 4.1 Happy Path: Erfolgreiche Aufgabenverarbeitung

```
 Client          Dispatcher        Namensdienst          Worker
    │                 │                  │                  │
    │  PostTask       │                  │                  │
    │ ──────────────► │                  │                  │
    │                 │  LookupWorker    │                  │
    │                 │ ───────────────► │                  │
    │                 │  [Worker-Liste]  │                  │
    │                 │ ◄─────────────── │                  │
    │                 │                  │                  │
    │                 │  ProcessTask     │                  │
    │                 │ ──────────────────────────────────► │
    │                 │  accepted=true   │                  │
    │                 │ ◄────────────────────────────────── │
    │  task_id=42     │                  │  [verarbeitet]   │
    │ ◄────────────── │                  │                  │
    │                 │  ReturnResult    │                  │
    │                 │ ◄────────────────────────────────── │
    │                 │  [task_id=42,    │                  │
    │                 │   success=true,  │                  │
    │                 │   result=...]    │                  │
    │                 │                  │                  │
    │  GetResult      │                  │                  │
    │ ──────────────► │                  │                  │
    │  status=COMPLETED, result=...      │                  │
    │ ◄────────────── │                  │                  │
```

**Zustandsübergänge (Task):**
`CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED`

---

### 4.2 Fehlerszenarien

#### Szenario A: Worker-Absturz / Timeout

```
 Client          Dispatcher        Namensdienst       Worker (tot)
    │                 │                  │                  │
    │  PostTask       │                  │                  │
    │ ──────────────► │                  │                  │
    │                 │  LookupWorker    │                  │
    │                 │ ───────────────► │                  │
    │                 │ ◄─────────────── │                  │
    │                 │  ProcessTask     │                  │
    │                 │ ──────────────────────────────────► │
    │                 │  accepted=true   │                  │
    │                 │ ◄────────────────────────────────── │
    │  task_id=42     │                  │                  │
    │ ◄────────────── │                  │                  │
    │                 │                  │      [ABSTURZ]   ✗
    │                 │  [Timeout-Checker, alle 5s]         │
    │                 │  Task 42: > TASK_TIMEOUT_SEC        │
    │                 │  → TIMEOUT → RETRYING → QUEUED      │
    │                 │                  │                  │
    │                 │  LookupWorker    │                  │
    │                 │ ───────────────► │                  │
    │                 │  [anderer Worker]│                  │
    │                 │ ◄─────────────── │                  │
    │                 │  ProcessTask     │                  │
    │                 │ ──────────────────────────────────► │
    │                 │  ReturnResult    │                  │
    │                 │ ◄────────────────────────────────── │
    │  status=COMPLETED                  │                  │
    │ ◄────────────── │                  │                  │
```

**Zustandsübergänge:**
`DISPATCHED → TIMEOUT → RETRYING → QUEUED → DISPATCHED → PROCESSING → COMPLETED`

Bei Erschöpfung aller Retries:
`TIMEOUT → RETRYING → QUEUED → ... → TIMEOUT → FAILED`

---

#### Szenario B: Worker lehnt Aufgabe ab (Kapazität voll)

```
 Client          Dispatcher        Namensdienst       Worker (voll)
    │                 │                  │                  │
    │  PostTask       │                  │                  │
    │ ──────────────► │                  │                  │
    │                 │  LookupWorker    │                  │
    │                 │ ───────────────► │                  │
    │                 │ ◄─────────────── │                  │
    │                 │  ProcessTask     │                  │
    │                 │ ──────────────────────────────────► │
    │                 │  accepted=false  │                  │
    │                 │ ◄────────────────────────────────── │
    │                 │  [Task bleibt QUEUED,               │
    │                 │   erneuter Dispatch im              │
    │                 │   nächsten Zyklus]                  │
```

---

#### Szenario C: Unbekannter Aufgabentyp

```
 Client          Dispatcher        Namensdienst
    │                 │                  │
    │  PostTask       │                  │
    │  type="unknown" │                  │
    │ ──────────────► │                  │
    │                 │  LookupWorker    │
    │                 │  type="unknown"  │
    │                 │ ───────────────► │
    │                 │  success=false,  │
    │                 │  workers=[]      │
    │                 │ ◄─────────────── │
    │  success=false, │                  │
    │  "kein Worker   │                  │
    │   für Typ"      │                  │
    │ ◄────────────── │                  │
```

**Ergebnis:** Task wird nicht erstellt; Client erhält sofort eine Fehlermeldung.
