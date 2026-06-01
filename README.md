# TaskGrid+

Erweitererbares Aufgabenverarbeitungssystem in Containern — Prüfungsaufgabe Verteilte Systeme (TIK23)

## Systemübersicht

TaskGrid+ ist ein verteiltes System zur dynamischen Aufgabenverarbeitung. Ein Client sendet Aufgaben an einen Dispatcher, der sie über einen selbst implementierten Namensdienst an geeignete Worker verteilt. Alle Komponenten laufen in separaten Docker-Containern und kommunizieren ausschließlich über gRPC.

```
┌─────────┐        ┌────────────┐        ┌──────────────┐
│  Client │──────► │ Dispatcher │──────► │   Worker(s)  │
└─────────┘        └─────┬──────┘        └──────────────┘
                         │                      │
                         ▼                      ▼
                  ┌─────────────┐        ┌──────────────┐
                  │ Namensdienst│◄───────│  Heartbeat   │
                  └─────────────┘        └──────────────┘
```

## Komponenten

| Komponente    | Beschreibung |
|---------------|-------------|
| **Client**    | Sendet Aufgaben an den Dispatcher, fragt Ergebnisse ab |
| **Dispatcher** | Zentrale Koordinationskomponente — verwaltet Queue, Task-Zustände, verteilt Aufgaben |
| **Worker**    | Spezialisierte Verarbeitungseinheit — registriert sich beim Namensdienst, verarbeitet Aufgaben |
| **Namensdienst** | Service-Discovery-Komponente — verwaltet Worker-Registrierungen, Heartbeats, Lookup |
| **Monitoring** | Statusübersicht über Worker, Tasks und Systemmetriken |

## Technologie-Stack

- **Sprache:** Python 3.12
- **Kommunikation:** gRPC (Protocol Buffers)
- **Containerisierung:** Docker + Docker Compose
- **Logging:** Strukturierte Logs mit `task_id` und `request_id`

## Unterstützte Aufgabentypen

| Typ        | Beschreibung |
|------------|-------------|
| `reverse`  | String umdrehen |
| `sum`      | Zahlen summieren |
| `hash`     | SHA256-Berechnung |
| `upper`    | Großschreibung |
| `wait`     | Künstliche Verzögerung (Lastsimulation) |
| `wordcount`| Wörter zählen (optional) |
| `lower`    | Kleinschreibung (optional) |
| `base64`   | Base64-Kodierung (optional) |
| `prime`    | Primzahlprüfung (optional) |

## Schnellstart

```bash
# Alle Komponenten starten
docker compose up --build

# Mehrere Worker eines Typs starten
docker compose up --scale worker-sum=3

# System stoppen
docker compose down
```

## Startanleitung

### Konfiguration

Alle Komponenten werden über Umgebungsvariablen konfiguriert. Die Standardwerte sind für eine lokale Docker-Compose-Umgebung vorbelegt.

#### Dispatcher

| Variable | Standardwert | Beschreibung |
|----------|-------------|-------------|
| `DISPATCHER_PORT` | `50051` | gRPC-Port des Dispatchers |
| `NAMESERVICE_ADDR` | `nameservice:50052` | Adresse des Namensdienstes |
| `TASK_TIMEOUT_SEC` | `60` | Timeout in Sekunden, nach dem ein nicht beantworteter Task erneut eingeplant wird |
| `MAX_RETRIES` | `3` | Maximale Anzahl an Wiederholungsversuchen pro Task; bei Überschreitung wird der Task auf `FAILED` gesetzt |
| `LOG_LEVEL` | `INFO` | Log-Level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_DIR` | *(leer)* | Optionales Verzeichnis für Log-Dateien |

#### Namensdienst

| Variable | Standardwert | Beschreibung |
|----------|-------------|-------------|
| `NAMESERVICE_PORT` | `50052` | gRPC-Port des Namensdienstes |
| `HEARTBEAT_TIMEOUT_SEC` | `30` | Zeit in Sekunden, nach der ein Worker ohne Heartbeat als inaktiv gilt |

#### Worker

| Variable | Standardwert | Beschreibung |
|----------|-------------|-------------|
| `WORKER_PORT` | `50053` | gRPC-Port des Workers |
| `NAMESERVICE_ADDR` | `nameservice:50052` | Adresse des Namensdienstes |
| `DISPATCHER_ADDR` | `dispatcher:50051` | Adresse des Dispatchers |
| `TASK_TYPE` | *(erforderlich)* | Tasktyp, den dieser Worker verarbeitet (z. B. `sum`, `reverse`) |

## Projektstruktur

```
taskgrid-plus/
├── client/             # Client-Komponente
├── dispatcher/         # Dispatcher-Komponente
├── worker/             # Worker-Komponente (mehrere Instanzen möglich)
├── nameservice/        # Namensdienst / Service Discovery
├── monitoring/         # Monitoring-Komponente
├── proto/              # gRPC Protobuf-Definitionen (geteilte Schnittstellen)
├── docs/               # Dokumentation, Architekturdiagramme, ADRs
├── docker-compose.yml
└── README.md
```

## Dokumentation

Die vollständige Architekturdokumentation, Schnittstellenbeschreibungen und Architecture Decision Records (ADRs) befinden sich im Verzeichnis [`docs/`](docs/).

## Abgabe

**Abgabedatum:** 08.06.2026 EOB  
**Kurs:** Verteilte Systeme — TIK23  
**Dozent:** Kevin Dallmann
