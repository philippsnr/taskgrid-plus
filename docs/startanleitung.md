# Startanleitung — TaskGrid+

## 1. Voraussetzungen

| Werkzeug | Mindestversion | Zweck |
|----------|---------------|-------|
| Docker | 24.0 | Container-Runtime |
| Docker Compose | 2.20 (Plugin) | Orchestrierung aller Dienste |
| Python | 3.12 | Nur für lokale Entwicklung ohne Docker |
| `grpcio-tools` | aktuell | Nur zum Neuerzeugen der Proto-Bindings |

Docker Compose ist ab Docker Desktop 3.x als Plugin enthalten (`docker compose`). Die ältere Standalone-Variante (`docker-compose`) funktioniert ebenfalls.

---

## 2. Build-Prozess

### 2.1 gRPC-Bindings aus `taskgrid.proto` generieren

Die generierten Dateien (`proto/taskgrid_pb2.py`, `proto/taskgrid_pb2_grpc.py`) sind bereits im Repository enthalten und müssen nur neu erzeugt werden, wenn das Schema geändert wird.

```bash
# Einmalig: grpcio-tools installieren
pip install grpcio-tools

# Proto-Bindings neu generieren (aus dem Repo-Root ausführen)
bash proto/compile_proto.sh
```

Das Skript ruft intern auf:
```bash
python -m grpc_tools.protoc \
  --proto_path=proto \
  --python_out=proto \
  --grpc_python_out=proto \
  proto/taskgrid.proto
```

### 2.2 Alle Docker-Images bauen

```bash
docker compose build
```

Dieser Schritt installiert automatisch alle Abhängigkeiten in die Images. Ein separates `pip install` auf dem Host ist für den produktiven Betrieb nicht nötig.

---

## 3. Startanleitung

### 3.1 Vollständiges System starten

```bash
docker compose up --build
```

`--build` stellt sicher, dass alle Images vor dem Start aktuell gebaut werden. Beim ersten Start empfehlenswert; danach reicht `docker compose up`.

**Startreihenfolge (automatisch via `depends_on` + Healthchecks):**
1. Namensdienst (Port 50052)
2. Dispatcher (Port 50051) — wartet bis Namensdienst healthy
3. Worker (`reverse`, `sum`, `hash`, `upper`, `wait`) — warten bis Dispatcher healthy
4. Monitoring — wartet bis Dispatcher und Namensdienst healthy

### 3.2 Worker skalieren

Mehrere Instanzen desselben Typs können parallel gestartet werden:

```bash
# 3 Sum-Worker starten
docker compose up --scale worker-sum=3

# Mehrere Typen gleichzeitig skalieren
docker compose up --scale worker-sum=3 --scale worker-reverse=2
```

Der Dispatcher wählt automatisch per Least-Load-Strategie unter den verfügbaren Instanzen aus.

### 3.3 Aufgabe einreichen (Client)

Der Client ist als einmaliges Kommandozeilenwerkzeug konzipiert (`profiles: [tools]`):

```bash
# Task senden
docker compose run --rm client send reverse "Hello World"
# Ausgabe: Task submitted: task_id=1

# Ergebnis abfragen
docker compose run --rm client result 1
# Ausgabe: Task 1: COMPLETED — "dlroW olleH"
```

**Unterstützte Aufgabentypen:**

| Typ | Beispiel-Payload | Beispiel-Ergebnis |
|-----|-----------------|------------------|
| `reverse` | `"Hello"` | `"olleH"` |
| `sum` | `"1,2,3,4"` | `"10"` |
| `hash` | `"hello"` | `"2cf24dba..."` (SHA-256) |
| `upper` | `"hello"` | `"HELLO"` |
| `wait` | `"3"` | `"waited 3s"` (3 s Verzögerung) |
| `wordcount` | `"hello world"` | `"2"` |
| `lower` | `"HELLO"` | `"hello"` |
| `base64` | `"hello"` | `"aGVsbG8="` |
| `prime` | `"17"` | `"true"` |

### 3.4 Monitoring aufrufen

Der Monitoring-Dienst gibt alle `WATCH_INTERVAL_SEC` Sekunden (Standard: 5 s) eine Statustabelle aus:

```bash
# Logs des Monitoring-Containers verfolgen
docker compose logs -f monitoring
```

Beispielausgabe:
```
+------------------------------------------+

|  TaskGrid+ Status  2026-06-02 12:00:00   |
+------------------------------------------+

|  Workers registered                     5|
|  Workers active                         5|
|  Supported task types  hash, reverse, ...|
+------------------------------------------+

|  Tasks queued                           0|
|  Tasks running                          2|
|  Tasks completed                       42|
|  Tasks failed                           1|
+------------------------------------------+

|  Avg processing time (ms)           123.4|
|  Total timeouts                         0|
|  Total retries                          1|
+------------------------------------------+
```

Alternativ: Monitoring einmalig manuell abfragen:

```bash
docker compose run --rm -e WATCH_INTERVAL_SEC=0 monitoring
```

### 3.5 System stoppen

```bash
# Alle Container stoppen und entfernen
docker compose down

# Auch Volumes entfernen (löscht Dispatcher-Logs)
docker compose down -v
```

---

## 4. Technologieliste

### Kernsprache

| Technologie | Version | Zweck |
|-------------|---------|-------|
| Python | 3.12 | Implementierungssprache aller Komponenten |

### Kommunikation

| Bibliothek | Version | Zweck |
|------------|---------|-------|
| `grpcio` | aktuell (pip) | gRPC-Laufzeitumgebung — Client/Server-Implementierung |
| `protobuf` | aktuell (pip) | Protocol Buffers Serialisierung/Deserialisierung |
| `grpcio-tools` | aktuell (pip) | Proto-Compiler (`grpc_tools.protoc`) — nur zur Entwicklungszeit |

### Infrastruktur

| Technologie | Version | Zweck |
|-------------|---------|-------|
| Docker | 24.0+ | Container-Isolation und -Deployment |
| Docker Compose | 2.20+ | Orchestrierung, Service-Abhängigkeiten, Skalierung |

### Standardbibliotheken (keine zusätzliche Installation)

| Modul | Zweck |
|-------|-------|
| `threading` | Nebenläufigkeit (Heartbeat-Thread, Task-Threads, Timeout-Checker) |
| `grpc` | (Teil von `grpcio`) gRPC-Kanal und Fehlertypen |
| `hashlib` | SHA-256-Berechnung im `hash`-Worker |
| `base64` | Base64-Kodierung im `base64`-Worker |
| `dataclasses` | `TaskRecord`-Datenstruktur im Dispatcher |
| `collections.deque` | Thread-sichere FIFO-Queue |
| `signal` | Graceful-Shutdown-Handler (SIGTERM/SIGINT) |

---

## 5. Lokale Entwicklung (ohne Docker)

Für die Entwicklung einzelner Komponenten außerhalb von Docker:

```bash
# Abhängigkeiten installieren
pip install grpcio protobuf grpcio-tools

# Namensdienst starten (Terminal 1)
python nameservice/main.py

# Dispatcher starten (Terminal 2)
NAMESERVICE_ADDR=localhost:50052 python dispatcher/main.py

# Worker starten (Terminal 3)
WORKER_TYPE=reverse WORKER_ID=worker-reverse-1 \
NAMESERVICE_ADDRESS=localhost DISPATCHER_ADDRESS=localhost \
python worker/main.py

# Task senden (Terminal 4)
python client/main.py send reverse "Hello World"
python client/main.py result 1
```

---

## 6. Konfigurationsreferenz

Alle Komponenten werden ausschließlich über Umgebungsvariablen konfiguriert:

| Komponente | Variable | Standard | Beschreibung |
|------------|----------|---------|-------------|
| Dispatcher | `DISPATCHER_PORT` | `50051` | gRPC-Port |
| Dispatcher | `NAMESERVICE_ADDR` | `nameservice:50052` | Adresse des Namensdienstes |
| Dispatcher | `TASK_TIMEOUT_SEC` | `60` | Timeout pro Task in Sekunden |
| Dispatcher | `MAX_RETRIES` | `3` | Maximale Retry-Versuche |
| Dispatcher | `LOG_LEVEL` | `INFO` | Log-Level |
| Dispatcher | `LOG_DIR` | *(leer)* | Optionales Log-Verzeichnis |
| Namensdienst | `NAMESERVICE_PORT` | `50052` | gRPC-Port |
| Namensdienst | `HEARTBEAT_TIMEOUT_SEC` | `30` | Sekunden bis `UNHEALTHY` |
| Worker | `WORKER_TYPE` | *(Pflicht)* | Aufgabentyp des Workers |
| Worker | `WORKER_PORT` | `50053` | gRPC-Port |
| Worker | `WORKER_ID` | *(Pflicht)* | Eindeutige Worker-ID |
| Worker | `NAMESERVICE_ADDRESS` | `localhost` | Hostname des Namensdienstes |
| Worker | `DISPATCHER_ADDRESS` | `localhost` | Hostname des Dispatchers |
| Worker | `HEARTBEAT_INTERVAL_SEC` | `10` | Heartbeat-Intervall in Sekunden |
| Monitoring | `DISPATCHER_ADDR` | `localhost:50051` | Adresse des Dispatchers |
| Monitoring | `NAMESERVICE_ADDR` | `localhost:50052` | Adresse des Namensdienstes |
| Monitoring | `WATCH_INTERVAL_SEC` | `0` | Abfrageintervall (0 = einmalig) |
| Client | `DISPATCHER_HOST` | `localhost` | Hostname des Dispatchers |
| Client | `DISPATCHER_PORT` | `50051` | Port des Dispatchers |
