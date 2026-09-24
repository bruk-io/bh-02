"""Threat lists for brig sandboxing.

Threat lists ship as documented tuples that the embedder folds in explicitly,
per SPEC.md §5.

## Threat classes

`CREDENTIAL_READ_DENIES_HOME_RELATIVE` — Home directory paths that must not
be readable by jailed processes, as they carry credentials or sensitive
authentication material (SSH keys, AWS credentials, GnuPG keyring, API tokens,
cloud configuration, etc.). Reading these exfiltrates the host's authentication
surface.

`SELF_MODIFY_WORKSPACE_RELATIVE` — Workspace (current working directory) paths
that must not be writable by jailed processes. A jail that can write `.git/hooks`,
`.envrc`, or an agent config file inside its granted workspace executes code
*outside* the jail later — a self-escalation threat. This is the threat
`write_denies` was introduced to contain, new relative to prior art in the
parent project.

`BARE_REPO_TOPLEVEL` — Git repository internal paths at the workspace root.
Creating `HEAD`, `objects`, or `refs` at the workspace root turns it into a
bare git repository, silently changing what every later git command means —
a workspace capture threat that should raise alerts.

## Special cases

`.claude` appears in both `CREDENTIAL_READ_DENIES_HOME_RELATIVE` and
`SELF_MODIFY_WORKSPACE_RELATIVE`. It is credential-bearing when read under
`$HOME` (harboring API tokens, workspace configuration), and self-modifying
when written inside a workspace (an agent config file that later executes
outside the jail).
"""

from typing import Final

CREDENTIAL_READ_DENIES_HOME_RELATIVE: Final[tuple[str, ...]] = (
    ".ssh",
    ".aws",
    ".gnupg",
    ".netrc",
    ".config/gh",
    ".docker",
    ".kube",
    ".npmrc",
    ".git-credentials",
    ".config/gcloud",
    ".claude",
    ".claude.json",
)

SELF_MODIFY_WORKSPACE_RELATIVE: Final[tuple[str, ...]] = (
    ".git/hooks",
    ".git/config",
    ".bashrc",
    ".zshrc",
    ".profile",
    ".envrc",
    ".vscode",
    ".idea",
    "AGENTS.md",
    "CLAUDE.md",
    ".claude",
)

BARE_REPO_TOPLEVEL: Final[tuple[str, ...]] = ("HEAD", "objects", "refs")
