import os
import sys

def debug(message: str):
    """
    Print a debug message to stderr if ENVGUARD_DEBUG=1 or --debug is passed.
    """
    if os.environ.get("ENVGUARD_DEBUG") == "1":
        # Use a gray/faded color for debug logs if possible, or just plain text
        print(f"\033[90m[EnvGuard Debug] {message}\033[0m", file=sys.stderr)
