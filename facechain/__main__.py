import sys

from .cli import main

if __name__ == "__main__":
    # Windows consoles default to a legacy code page; force UTF-8 so titles / URLs render.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
