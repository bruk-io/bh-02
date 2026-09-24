"""Entry point for `python -m brig.mech.trampoline`.

Kept separate from `brig/mech/trampoline/__init__.py` so that importing the
package -- which the unit tests do directly, for `parse_trampoline_argv` and
`apply_limits` -- never runs `main()`. pypeeker's `import-time-side-effects`
rule treats a module-level `if` body as import-time unconditionally, so a
real `main()` guarded by `if __name__ == "__main__":` in a plain module is an
unavoidable finding under that rule even though the guard never actually
fires on a plain `import`; the fix is this split:
one file the tests import freely, one file that is never imported by
anything, only ever run.

Only actually running this file (as `-m` does) applies an rlimit or execs
anything.
"""

from __future__ import annotations

import sys

from brig.mech.trampoline import main

if __name__ == "__main__":
    sys.exit(main())
