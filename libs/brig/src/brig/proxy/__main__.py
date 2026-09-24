"""Entry point: `python -m brig.proxy`.

The `if __name__` guard lives here and nowhere else -- pypeeker treats a
module-level `if` body as import-time unconditionally, so a real `main()`
under that guard inside `server.py` would be an unavoidable
`import-time-side-effects` finding (CLAUDE.md).
"""

from __future__ import annotations

import sys

from brig.proxy.server import main

if __name__ == "__main__":
    sys.exit(main())
