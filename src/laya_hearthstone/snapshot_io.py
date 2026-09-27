"""Atomic snapshot replacement with bounded retries for Windows readers."""
from pathlib import Path
import time


def publish_text(path, text, attempts=10, delay=0.05):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    for attempt in range(attempts):
        try:
            temporary.write_text(text, encoding='utf-8')
            temporary.replace(path)
            return True
        except PermissionError:
            if attempt + 1 < attempts:
                time.sleep(delay)
    return False
