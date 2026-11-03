"""Print one eval task's payload, for the bash channel: what `./get_logs` and its siblings run.

The task comes from the environment, TOOL_OUTPUT_LAB_TASK (an id from `evals.tasks`), so the script
in the session's folder holds no hint of which case it is, and there is no payload file to read
around the fold: the output exists only as the command's stdout, as a real command's would.
"""

import os
import sys

from evals.tasks import task


def main() -> int:
    sys.stdout.write(task(os.environ["TOOL_OUTPUT_LAB_TASK"]).payload())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
