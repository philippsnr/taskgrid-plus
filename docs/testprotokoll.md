# Testprotokoll — Erfolgreiche Aufgaben

**Datum:** 2026-06-04  
**System:** TaskGrid+  
**Umgebung:** Docker Compose (Podman rootless), lokale Maschine

## Systemzustand beim Test

| Komponente          | Container-ID     | IP-Adresse  |
|---------------------|------------------|-------------|
| Nameservice         | taskgrid-plus-nameservice-1  | 10.89.0.10 |
| Dispatcher          | taskgrid-plus-dispatcher-1   | 10.89.0.11 |
| Worker `reverse`    | `58c35f0a9f88`               | 10.89.0.13 |
| Worker `sum`        | `f394568ef865`               | 10.89.0.14 |
| Worker `hash`       | `0e0c726b9706`               | 10.89.0.15 |
| Worker `upper`      | `a276953086f5`               | 10.89.0.16 |
| Worker `wait`       | `08fd4519f2fa`               | 10.89.0.17 |

Alle 5 Worker wurden beim Nameservice registriert.  
**Dispatcher-Status vor dem Test:** `workers_registered=5`, `workers_active=5`, `tasks_completed=0`

---

## Testfälle

### TC-01 — `reverse` „hello"

| Feld              | Wert |
|-------------------|------|
| **Typ**           | `reverse` |
| **Payload**       | `hello` |
| **task_id**       | `1` |
| **Erwartetes Ergebnis** | `olleh` |
| **Tatsächliches Ergebnis** | `olleh` ✓ |
| **Bearbeitender Worker** | `58c35f0a9f88` (10.89.0.13) |
| **Laufzeit (Worker)** | 5 ms |
| **End-to-End-Zeit** | 1828 ms |

**Status-Verlauf:**

```
CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED
```

**Dispatcher-Logs:**
```
[dispatcher] request_id=proto-1780567455331 task_id=1 status=CREATED type=reverse
[dispatcher] request_id=proto-1780567455331 task_id=1 status=QUEUED type=reverse
[dispatcher] request_id=8f887a76-4d6a-47dc-b54b-de8e6fe9f37e task_id=1 status=DISPATCHED worker=58c35f0a9f88
[dispatcher] request_id=8f887a76-4d6a-47dc-b54b-de8e6fe9f37e task_id=1 status=PROCESSING worker=58c35f0a9f88
[dispatcher] request_id=19a03998-14f3-4c65-8e3f-ab3b0e61f2da task_id=1 status=COMPLETED duration_ms=5
[dispatcher] request_id=19a03998-14f3-4c65-8e3f-ab3b0e61f2da task_id=1 event=RESULT_RECEIVED worker=58c35f0a9f88 success=True
```

**Worker-Logs (`worker-reverse`):**
```
[58c35f0a9f88] request_id=8f887a76-4d6a-47dc-b54b-de8e6fe9f37e task_id=1 status=RECEIVED type=reverse
[58c35f0a9f88] request_id=8f887a76-4d6a-47dc-b54b-de8e6fe9f37e task_id=1 status=PROCESSING type=reverse
[58c35f0a9f88] request_id=8f887a76-4d6a-47dc-b54b-de8e6fe9f37e task_id=1 status=COMPLETED
```

---

### TC-02 — `sum` „1,2,3,4"

| Feld              | Wert |
|-------------------|------|
| **Typ**           | `sum` |
| **Payload**       | `1,2,3,4` |
| **task_id**       | `2` |
| **Erwartetes Ergebnis** | `10` |
| **Tatsächliches Ergebnis** | `10` ✓ |
| **Bearbeitender Worker** | `f394568ef865` (10.89.0.14) |
| **Laufzeit (Worker)** | 6 ms |
| **End-to-End-Zeit** | 1527 ms |

**Status-Verlauf:**

```
CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED
```

**Dispatcher-Logs:**
```
[dispatcher] request_id=proto-1780567455640 task_id=2 status=CREATED type=sum
[dispatcher] request_id=proto-1780567455640 task_id=2 status=QUEUED type=sum
[dispatcher] request_id=2928e445-7051-48f4-b178-f9dcf87e0670 task_id=2 status=DISPATCHED worker=f394568ef865
[dispatcher] request_id=2928e445-7051-48f4-b178-f9dcf87e0670 task_id=2 status=PROCESSING worker=f394568ef865
[dispatcher] request_id=071f9a2f-3879-406f-8fea-00b4828772de task_id=2 status=COMPLETED duration_ms=6
[dispatcher] request_id=071f9a2f-3879-406f-8fea-00b4828772de task_id=2 event=RESULT_RECEIVED worker=f394568ef865 success=True
```

**Worker-Logs (`worker-sum`):**
```
[f394568ef865] request_id=2928e445-7051-48f4-b178-f9dcf87e0670 task_id=2 status=RECEIVED type=sum
[f394568ef865] request_id=2928e445-7051-48f4-b178-f9dcf87e0670 task_id=2 status=PROCESSING type=sum
[f394568ef865] request_id=2928e445-7051-48f4-b178-f9dcf87e0670 task_id=2 status=COMPLETED
```

---

### TC-03 — `hash` „hello"

| Feld              | Wert |
|-------------------|------|
| **Typ**           | `hash` |
| **Payload**       | `hello` |
| **task_id**       | `3` |
| **Erwartetes Ergebnis** | SHA-256 von „hello" |
| **Tatsächliches Ergebnis** | `2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824` ✓ |
| **Bearbeitender Worker** | `0e0c726b9706` (10.89.0.15) |
| **Laufzeit (Worker)** | 5 ms |
| **End-to-End-Zeit** | 1224 ms |

**Status-Verlauf:**

```
CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED
```

**Dispatcher-Logs:**
```
[dispatcher] request_id=proto-1780567455943 task_id=3 status=CREATED type=hash
[dispatcher] request_id=proto-1780567455943 task_id=3 status=QUEUED type=hash
[dispatcher] request_id=04b45709-0f7d-4ea2-81f7-456755b4e31a task_id=3 status=DISPATCHED worker=0e0c726b9706
[dispatcher] request_id=04b45709-0f7d-4ea2-81f7-456755b4e31a task_id=3 status=PROCESSING worker=0e0c726b9706
[dispatcher] request_id=09002f39-0e99-4b3f-a2a3-05ab89647537 task_id=3 status=COMPLETED duration_ms=5
[dispatcher] request_id=09002f39-0e99-4b3f-a2a3-05ab89647537 task_id=3 event=RESULT_RECEIVED worker=0e0c726b9706 success=True
```

**Worker-Logs (`worker-hash`):**
```
[0e0c726b9706] request_id=04b45709-0f7d-4ea2-81f7-456755b4e31a task_id=3 status=RECEIVED type=hash
[0e0c726b9706] request_id=04b45709-0f7d-4ea2-81f7-456755b4e31a task_id=3 status=PROCESSING type=hash
[0e0c726b9706] request_id=04b45709-0f7d-4ea2-81f7-456755b4e31a task_id=3 status=COMPLETED
```

---

### TC-04 — `upper` „hello world"

| Feld              | Wert |
|-------------------|------|
| **Typ**           | `upper` |
| **Payload**       | `hello world` |
| **task_id**       | `4` |
| **Erwartetes Ergebnis** | `HELLO WORLD` |
| **Tatsächliches Ergebnis** | `HELLO WORLD` ✓ |
| **Bearbeitender Worker** | `a276953086f5` (10.89.0.16) |
| **Laufzeit (Worker)** | 9 ms |
| **End-to-End-Zeit** | 921 ms |

**Status-Verlauf:**

```
CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED
```

**Dispatcher-Logs:**
```
[dispatcher] request_id=proto-1780567456249 task_id=4 status=CREATED type=upper
[dispatcher] request_id=proto-1780567456249 task_id=4 status=QUEUED type=upper
[dispatcher] request_id=c1d7a2fd-96e9-46c6-9fbb-92127b0c1315 task_id=4 status=DISPATCHED worker=a276953086f5
[dispatcher] request_id=c1d7a2fd-96e9-46c6-9fbb-92127b0c1315 task_id=4 status=PROCESSING worker=a276953086f5
[dispatcher] request_id=93d89078-0b1d-4bbe-81a6-060e1f6f53b8 task_id=4 status=COMPLETED duration_ms=9
[dispatcher] request_id=93d89078-0b1d-4bbe-81a6-060e1f6f53b8 task_id=4 event=RESULT_RECEIVED worker=a276953086f5 success=True
```

**Worker-Logs (`worker-upper`):**
```
[a276953086f5] request_id=c1d7a2fd-96e9-46c6-9fbb-92127b0c1315 task_id=4 status=RECEIVED type=upper
[a276953086f5] request_id=c1d7a2fd-96e9-46c6-9fbb-92127b0c1315 task_id=4 status=PROCESSING type=upper
[a276953086f5] request_id=c1d7a2fd-96e9-46c6-9fbb-92127b0c1315 task_id=4 status=COMPLETED
```

---

### TC-05 — `wait` „2"

| Feld              | Wert |
|-------------------|------|
| **Typ**           | `wait` |
| **Payload**       | `2` |
| **task_id**       | `5` |
| **Erwartetes Ergebnis** | `waited 2s` |
| **Tatsächliches Ergebnis** | `waited 2s` ✓ |
| **Bearbeitender Worker** | `08fd4519f2fa` (10.89.0.17) |
| **Laufzeit (Worker)** | 2013 ms |
| **End-to-End-Zeit** | 2625 ms |

**Status-Verlauf:**

```
CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED
```

**Dispatcher-Logs:**
```
[dispatcher] request_id=proto-1780567456552 task_id=5 status=CREATED type=wait
[dispatcher] request_id=proto-1780567456552 task_id=5 status=QUEUED type=wait
[dispatcher] request_id=8432ec8a-0935-4f6d-bb18-0224ee116948 task_id=5 status=DISPATCHED worker=08fd4519f2fa
[dispatcher] request_id=8432ec8a-0935-4f6d-bb18-0224ee116948 task_id=5 status=PROCESSING worker=08fd4519f2fa
[dispatcher] request_id=cec41f48-ee7f-4b94-a235-bb0960e060cc task_id=5 status=COMPLETED duration_ms=2013
[dispatcher] request_id=cec41f48-ee7f-4b94-a235-bb0960e060cc task_id=5 event=RESULT_RECEIVED worker=08fd4519f2fa success=True
```

**Worker-Logs (`worker-wait`):**
```
[08fd4519f2fa] request_id=8432ec8a-0935-4f6d-bb18-0224ee116948 task_id=5 status=RECEIVED type=wait
[08fd4519f2fa] request_id=8432ec8a-0935-4f6d-bb18-0224ee116948 task_id=5 status=PROCESSING type=wait
[08fd4519f2fa] request_id=8432ec8a-0935-4f6d-bb18-0224ee116948 task_id=5 status=COMPLETED
```

---

### TC-06 — `reverse` „taskgrid"

| Feld              | Wert |
|-------------------|------|
| **Typ**           | `reverse` |
| **Payload**       | `taskgrid` |
| **task_id**       | `6` |
| **Erwartetes Ergebnis** | `dirgksat` |
| **Tatsächliches Ergebnis** | `dirgksat` ✓ |
| **Bearbeitender Worker** | `58c35f0a9f88` (10.89.0.13) |
| **Laufzeit (Worker)** | 2 ms |
| **End-to-End-Zeit** | 312 ms |

**Status-Verlauf:**

```
CREATED → QUEUED → DISPATCHED → PROCESSING → COMPLETED
```

**Dispatcher-Logs:**
```
[dispatcher] request_id=proto-1780567456859 task_id=6 status=CREATED type=reverse
[dispatcher] request_id=proto-1780567456859 task_id=6 status=QUEUED type=reverse
[dispatcher] request_id=69b95574-355c-4ec6-b767-3f7f6d490335 task_id=6 status=DISPATCHED worker=58c35f0a9f88
[dispatcher] request_id=69b95574-355c-4ec6-b767-3f7f6d490335 task_id=6 status=PROCESSING worker=58c35f0a9f88
[dispatcher] request_id=c7f5e104-a9a3-4e66-812a-099a4b9f5cd5 task_id=6 status=COMPLETED duration_ms=2
[dispatcher] request_id=c7f5e104-a9a3-4e66-812a-099a4b9f5cd5 task_id=6 event=RESULT_RECEIVED worker=58c35f0a9f88 success=True
```

**Worker-Logs (`worker-reverse`):**
```
[58c35f0a9f88] request_id=69b95574-355c-4ec6-b767-3f7f6d490335 task_id=6 status=RECEIVED type=reverse
[58c35f0a9f88] request_id=69b95574-355c-4ec6-b767-3f7f6d490335 task_id=6 status=PROCESSING type=reverse
[58c35f0a9f88] request_id=69b95574-355c-4ec6-b767-3f7f6d490335 task_id=6 status=COMPLETED
```

---

## Gesamtübersicht

| TC   | Typ       | Payload        | Erwartet                      | Erhalten                      | Worker           | Status      |
|------|-----------|----------------|-------------------------------|-------------------------------|------------------|-------------|
| TC-01 | `reverse` | `hello`        | `olleh`                       | `olleh`                       | `58c35f0a9f88`  | COMPLETED ✓ |
| TC-02 | `sum`     | `1,2,3,4`      | `10`                          | `10`                          | `f394568ef865`  | COMPLETED ✓ |
| TC-03 | `hash`    | `hello`        | SHA-256-Hex                   | `2cf24dba...b9824`            | `0e0c726b9706`  | COMPLETED ✓ |
| TC-04 | `upper`   | `hello world`  | `HELLO WORLD`                 | `HELLO WORLD`                 | `a276953086f5`  | COMPLETED ✓ |
| TC-05 | `wait`    | `2`            | `waited 2s`                   | `waited 2s`                   | `08fd4519f2fa`  | COMPLETED ✓ |
| TC-06 | `reverse` | `taskgrid`     | `dirgksat`                    | `dirgksat`                    | `58c35f0a9f88`  | COMPLETED ✓ |

**Ergebnis: 6/6 Aufgaben erfolgreich abgeschlossen.**

## Dispatcher-Status nach dem Test

```
workers_registered : 5
workers_active     : 5
supported_types    : [hash, reverse, sum, upper, wait]
tasks_queued       : 0
tasks_running      : 0
tasks_completed    : 6
tasks_failed       : 0
avg_processing_ms  : 340.0
total_timeouts     : 0
total_retries      : 0
```
