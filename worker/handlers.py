"""
Task type handlers for Worker.

Data-driven handler registration. Each handler processes a specific task type:
- Receives: payload (string)
- Returns: (success: bool, result: str)

To add a new task type:
1. Define a handler function with signature: handler(payload: str) -> tuple[bool, str]
2. Add it to the HANDLERS dict with the task type as key
3. Set WORKER_TYPE env var to the handler name at startup
4. Namensdienst learns the type from RegisterWorkerRequest
5. Dispatcher discovers workers for that type via LookupWorker
"""

import hashlib
import time


def handle_reverse(payload: str) -> tuple[bool, str]:
    """Reverse the input string.

    Example: "hello" → "olleh"
    """
    return True, payload[::-1]


def handle_sum(payload: str) -> tuple[bool, str]:
    """Sum a comma-separated list of numbers.
    
    Example: "1,2,3,4" → "10"
    """
    try:
        # Parse comma-separated numbers
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
        
        total = sum(numbers)

        if total.is_integer():
            return True, str(int(total))
        return True, str(total)
    except Exception as e:
        return False, f"Sum failed: {str(e)}"


def handle_hash(payload: str) -> tuple[bool, str]:
    """Compute SHA-256 hash of the payload.

    Example: "hello" → "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    """
    return True, hashlib.sha256(payload.encode('utf-8')).hexdigest()


def handle_upper(payload: str) -> tuple[bool, str]:
    """Convert string to uppercase.

    Example: "hello world" → "HELLO WORLD"
    """
    return True, payload.upper()


def handle_wait(payload: str) -> tuple[bool, str]:
    """Sleep for N seconds and return confirmation.
    
    Example: "3" → sleep 3 seconds → "waited 3s"
    
    Validates that payload is a positive number >= 0.
    """
    try:
        # Parse seconds from payload
        payload_stripped = payload.strip()
        if not payload_stripped:
            return False, "Payload cannot be empty"
        
        try:
            seconds = float(payload_stripped)
        except ValueError:
            return False, f"Invalid number: '{payload_stripped}'"
        
        if seconds < 0:
            return False, f"Duration cannot be negative: {seconds}"
        
        # Cap at reasonable limit (e.g., 1 hour) to prevent abuse
        max_seconds = 3600
        if seconds > max_seconds:
            return False, f"Duration exceeds max ({max_seconds}s): {seconds}"
        
        # Sleep for the specified duration
        time.sleep(seconds)
        
        if seconds.is_integer():
            return True, f"waited {int(seconds)}s"
        return True, f"waited {seconds}s"
    except Exception as e:
        return False, f"Wait failed: {str(e)}"


# ─── Handler Registry ─────────────────────────────────────────────────────────

HANDLERS = {
    "reverse": handle_reverse,
    "sum": handle_sum,
    "hash": handle_hash,
    "upper": handle_upper,
    "wait": handle_wait,
}

SUPPORTED_TYPES = list(HANDLERS.keys())


def get_handler(task_type: str):
    """Get handler function for a task type.
    
    Args:
        task_type: The task type name (e.g., "reverse", "sum")
        
    Returns:
        Handler function, or None if not found
    """
    return HANDLERS.get(task_type)


def handle_task(task_type: str, payload: str) -> tuple[bool, str]:
    """Dispatch task to appropriate handler.
    
    Args:
        task_type: The task type (must be in HANDLERS)
        payload: The task payload string
        
    Returns:
        (success: bool, result: str)
    """
    handler = get_handler(task_type)
    if handler is None:
        return False, f"Unknown task type: {task_type}"
    
    return handler(payload)
