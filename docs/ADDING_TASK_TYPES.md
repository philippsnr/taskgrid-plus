# Adding New Task Types

This guide explains how to add a new task type handler to the Worker without modifying the Dispatcher.

## Architecture

TaskGrid uses a **data-driven handler registration system**:

1. All task handlers are registered in a HANDLERS dictionary in `worker/handlers.py`
2. Each worker declares its supported task type via the `WORKER_TYPE` environment variable at startup
3. The Namensdienst learns the type via the `RegisterWorkerRequest`
4. The Dispatcher discovers workers for a task type via `LookupWorker` to the Namensdienst
5. No Dispatcher code changes needed when adding new types

## Adding a New Handler

### Step 1: Define the Handler Function

Add a new handler function to `worker/handlers.py`:

```python
def handle_mytype(payload: str) -> tuple[bool, str]:
    """Brief description of what this handler does.
    
    Example: "input" → "output"
    """
    try:
        # Your implementation
        result = process(payload)
        return True, result
    except Exception as e:
        return False, f"Error: {str(e)}"
```

**Key requirements:**
- Function signature: `handle_<typename>(payload: str) -> tuple[bool, str]`
- Returns: `(success: bool, result: str)`
  - If `success=True`: `result` is the task result
  - If `success=False`: `result` is the error message
- Validate input and handle errors gracefully
- Never raise exceptions (catch and return False with error message)

### Step 2: Register the Handler

Add your handler to the `HANDLERS` dictionary in `worker/handlers.py`:

```python
HANDLERS = {
    "reverse": handle_reverse,
    "sum": handle_sum,
    "hash": handle_hash,
    "upper": handle_upper,
    "wait": handle_wait,
    "mytype": handle_mytype,  # ← Add your handler here
}
```

The key in the dictionary is the task type name that will be used in:
- Client requests: `PostTask(type="mytype", payload="...")`
- Worker registration: `WORKER_TYPE=mytype`
- Dispatcher routing

### Step 3: Start a Worker with the New Type

Start a worker container with the new handler:

```bash
export WORKER_ID=worker-mytype-1
export WORKER_TYPE=mytype
python worker/main.py
```

The worker will:
1. Validate that `mytype` is in the supported types
2. Load the handler
3. Register with Namensdienst as type `mytype`
4. Begin accepting tasks of type `mytype` from Dispatcher

### Step 4: Send Tasks

Clients and the Dispatcher can now send tasks of this type:

```python
# Client example
client.post_task(type="mytype", payload="input_data")
```

## Example: Adding a "multiply" Handler

### 1. Add handler to `worker/handlers.py`:

```python
def handle_multiply(payload: str) -> tuple[bool, str]:
    """Multiply a comma-separated list of numbers.
    
    Example: "2,3,4" → "24"
    """
    try:
        parts = payload.split(",")
        numbers = []
        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue
            try:
                numbers.append(float(stripped))
            except ValueError:
                return False, f"Invalid number: '{stripped}'"
        
        if not numbers:
            return False, "No valid numbers found"
        
        result = 1
        for n in numbers:
            result *= n
        
        if result == int(result):
            return True, str(int(result))
        else:
            return True, str(result)
    except Exception as e:
        return False, f"Multiply failed: {str(e)}"
```

### 2. Register in HANDLERS:

```python
HANDLERS = {
    "reverse": handle_reverse,
    "sum": handle_sum,
    "hash": handle_hash,
    "upper": handle_upper,
    "wait": handle_wait,
    "multiply": handle_multiply,  # ← New handler
}
```

### 3. Start worker:

```bash
WORKER_ID=worker-multiply-1 WORKER_TYPE=multiply python worker/main.py
```

### 4. Send task:

```python
client.post_task(type="multiply", payload="2,3,4")
# Result: "24"
```

## Testing Your Handler

Test the handler directly before deploying:

```python
from worker.handlers import handle_task

success, result = handle_task("mytype", "test_payload")
if success:
    print(f"Result: {result}")
else:
    print(f"Error: {result}")
```

## Error Handling Best Practices

1. **Validate input** - Check for empty payloads, invalid formats, etc.
2. **Return meaningful errors** - Include details about what went wrong
3. **Handle edge cases** - Test with empty strings, very large numbers, special characters, etc.
4. **Implement limits** - Cap execution time, memory usage, output size if needed
5. **Be idempotent** - Tasks may be retried; avoid side effects

### Example Error Handling:

```python
def handle_process(payload: str) -> tuple[bool, str]:
    # Validate input
    if not payload or not payload.strip():
        return False, "Payload cannot be empty"
    
    # Validate format
    if not payload.isdigit():
        return False, f"Expected digits, got: {payload}"
    
    # Check limits
    num = int(payload)
    if num > 1_000_000:
        return False, f"Input exceeds maximum: {num} > 1000000"
    
    # Process
    try:
        result = expensive_operation(num)
        return True, str(result)
    except TimeoutError:
        return False, "Processing timeout"
    except Exception as e:
        return False, f"Processing failed: {str(e)}"
```

## Architecture Implications

### No Dispatcher Changes Required

1. ✓ Dispatcher doesn't have a hardcoded list of task types
2. ✓ Dispatcher learns available workers via Namensdienst lookup
3. ✓ Worker type is declared at startup via `WORKER_TYPE` env var
4. ✓ Multiple workers can handle the same type (load balancing)
5. ✓ Easy to scale: `docker-compose up --scale worker-mytype=3`

### Docker Compose

To scale a new task type in Docker Compose:

```yaml
services:
  worker-mytype:
    image: taskgrid:worker
    environment:
      WORKER_ID: worker-mytype-${COMPOSE_SERVICE_NUMBER}
      WORKER_TYPE: mytype
      NAMESERVICE_ADDRESS: nameservice
      DISPATCHER_ADDRESS: dispatcher
    depends_on:
      - nameservice
      - dispatcher
```

Deploy with:

```bash
docker-compose up --scale worker-mytype=5
```

## Supported Built-in Types

Current handlers:

| Type | Handler | Example |
|------|---------|---------|
| `reverse` | Reverses a string | `"hello"` → `"olleh"` |
| `sum` | Sums comma-separated numbers | `"1,2,3,4"` → `"10"` |
| `hash` | SHA-256 hash of payload | `"hello"` → `"2cf24dba..."` |
| `upper` | Converts to uppercase | `"hello"` → `"HELLO"` |
| `wait` | Sleeps N seconds | `"3"` → sleeps, returns `"waited 3s"` |

## See Also

- [Worker Implementation](../worker/worker.py) - Base Worker class
- [Handler Registry](../worker/handlers.py) - All handlers and registration
- [Main Entry Point](../worker/main.py) - TaskWorker that dispatches to handlers
