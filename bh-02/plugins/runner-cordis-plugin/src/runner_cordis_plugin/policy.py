"""What bh-02 means the confined runner's jail to keep and allow: `Policy`, bh-02's own intent,
and the pure functions that make it. No brig here: `spec_for` is the whole policy, `brig_spec`
turns a `Policy` into brig's policies, and `jail` is the shell.

What an input may write: the project root (`write`) and a scratch directory of the jail's own.
What it may not, even inside those: the composition's layer files (an input rewriting one would
reshape the program running it, outside the jail), every path the host imports code from
(`sys.path` entries and the interpreter's prefix), the interpreter bh-02 runs on (its files: in a
venv layout the base's binary is on neither of those, and the next start on the host would run
what an input wrote there; and the directory of every link on the way to it, which a mount on the
file cannot hold: an input could rename the link and plant a Python of its own at its name), the
directory of every package bh-02 runs code from (`code`: bh-02's own, cordis's, brig's and each
plugin's, as installed; under a writable root when bh-02 works on its own checkout, an editable
install), whose modules bh-02 imports in its own process, the self-modification list
(`SELF_MODIFYING`: `.git/hooks`, `.git/config`, shell rc files, `.envrc`, ...; the guidance files,
`GUIDANCE`, are not on it), any secret below
under a writable root (it may not replace what it can't read), and bh-02's configuration
directories under one (`trusted`: the person's `$XDG_CONFIG_HOME/bh-02` and `~/.config/bh-02`,
when bh-02 runs from the home directory), whose models file and startup file a later session
reads on the host and trusts. What it may not read: the credential paths under the home directory
(`CREDENTIALS`), `hide` under the project (nothing by default), and what the `host` value names as
`secrets` (the sessions' state, where Claude Code keeps its tokens). No network: the program's
own socket (a channel brig reserves) is the one way in or out. The worker's environment is exactly a
short allowlist: brig is handed bh-02's environment as the candidate and lets through the names
the policy lists (`brig_spec.to_brig`), so a variable of the launching shell (a `CLAUDE_*` of a Claude
Code that launched bh-02, a key the person exports for a model) reaches no worker unless `env` lists it.

What the person grants (`grants.Grants`: decision-0012) adds to that, after the floor: a read grant is
a readable root, a write grant a writable root (the one way past the self-modification list is a
write grant on that exact path), an env grant a name on the allow-list. `spec_for` checks each
against the floor first, with the path resolved, and what it refuses it says (`Policy.refused`); a
net grant is `brig_spec.to_brig`'s.

`spec_for` is what bh-02 means; the jail reads by allowlist (`allowlisted`), and a Linux jail is the
only one there is.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from runner_cordis_plugin.grants import NO_GRANTS, Floor, Grant, Grants, Invalid, Kind, refusal

__all__ = [
    "BASELINE_ENV",
    "CREDENTIALS",
    "GUIDANCE",
    "SELF_MODIFYING",
    "BrigConfig",
    "Policy",
    "admitted",
    "allowlisted",
    "git_author",
    "link_directories",
    "readable_roots",
    "socket_refusal",
    "spec_for",
    "told_reads",
]


def _paths(paths: Sequence[str]) -> tuple[str, ...]:
    """Each path once, without a trailing `/`, sorted."""
    return tuple(sorted({p if p == "/" else p.rstrip("/") for p in paths} - {""}))


def _roots(paths: Sequence[str]) -> tuple[str, ...]:
    """`_paths`, less every root another one already contains: a tree named once."""
    kept = _paths(paths)
    return tuple(p for p in kept if not any(o != p and (o == "/" or p.startswith(o + "/")) for o in kept))


@dataclass(frozen=True, slots=True)
class Policy:
    """What bh-02 means a jail to do, as values: not how any jail does it. Paths are absolute.

    `writable`: the roots the program may write. `write_denies`: paths in or under them it may not.
    `readable`: the trees it may read (none until `allowlisted`). `masks`: what it may not read
    (the secrets). `env_allow`: the names
    of bh-02's own environment that survive; `env_set`: the variables it sets besides (`TMPDIR`,
    the git author).

    Each tuple is a set kept in order (`_paths`), `writable` and `readable` as trees (`_roots`),
    and `env_set` has one value per name, the last."""

    writable: tuple[str, ...]
    write_denies: tuple[str, ...]
    masks: tuple[str, ...]
    env_allow: tuple[str, ...]
    env_set: tuple[tuple[str, str], ...]
    readable: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "writable", _roots(self.writable))
        object.__setattr__(self, "write_denies", _paths(self.write_denies))
        object.__setattr__(self, "masks", _paths(self.masks))
        object.__setattr__(self, "readable", _roots(self.readable))
        object.__setattr__(self, "env_allow", tuple(sorted(set(self.env_allow))))
        object.__setattr__(self, "env_set", tuple(sorted(dict(self.env_set).items())))


#: What under a root an input may write it may not, unless a write grant names that exact path: a
#: path that runs code outside the jail later (git hooks and config, shell rc files, an `.envrc`,
#: editor and Claude settings). Relative to each root.
SELF_MODIFYING: tuple[str, ...] = (
    ".git/hooks",
    ".git/config",
    ".bashrc",
    ".zshrc",
    ".profile",
    ".envrc",
    ".vscode",
    ".idea",
    ".claude",
)

#: The project's guidance files: editing them is ordinary work, so an input may write them (they
#: steer the next session, but only through what the person reads and the model is told).
GUIDANCE: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md")


#: What under the home directory an input may not read: the person's credentials (keys, tokens,
#: cloud and registry logins, Claude Code's own). Relative to the home directory.
CREDENTIALS: tuple[str, ...] = (
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


#: The variables the jail always lets through: what a program needs to run at all.
BASELINE_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL", "TERM")


@dataclass(frozen=True, slots=True)
class BrigConfig:
    """`write`: where an input may write besides its scratch dir (relative to the python row's root).
    `deny`: more paths it may not write. `hide`: paths it may not read (relative to the root; none by
    default). `env`: the variables that survive the scrub; None (unset) is `BASELINE_ENV` plus the
    names of the person's `runner.toml` (`allowlist.effective`), a list here replaces that whole
    list. There is no `allow`: a self-modifying path is writable by a write grant on that exact
    path (decision-0012 item 10)."""

    write: Sequence[str] = (".",)
    deny: Sequence[str] = ()
    hide: Sequence[str] = ()
    env: Sequence[str] | None = None


def spec_for(
    *,
    root: str,
    scratch: str,
    home: str,
    config: BrigConfig,
    layers: Sequence[str],
    host: Sequence[str],
    secrets: Sequence[str] = (),
    trusted: Sequence[str] = (),
    code: Sequence[str] = (),
    interpreters: Sequence[str] = (),
    links: Sequence[str] = (),
    memory: str = "",
    store: str = "",
    grants: Grants = NO_GRANTS,
    key_envs: Mapping[str, Sequence[str]] | None = None,
) -> Policy:
    """The jail's `Policy`. `host` is every path the host process loads code from; any under a
    writable root is denied, as are the layer files and the self-modification list.
    `secrets` (absolute) may not be read, wherever they are. `trusted` (absolute directories:
    bh-02's configuration, whose files the host reads and trusts) and `code` (absolute: the
    directory of every package bh-02 runs code from) may not be written where they are under a
    writable root. `interpreters` (absolute, resolved: the files of the interpreter bh-02 itself
    runs on, `facts.interpreter_files`) may not be written where they are under one either, nor the
    directory of each of `links` (absolute: the links on the way to them, `facts.links_on_the_way`;
    `link_directories`). `memory` (absolute: the project's auto memory directory, '' for none) may be
    written, as a root of its own outside the project: no self-modification list applies there,
    since nothing reads it but the memory row, through no link. `store` (absolute: the grants store,
    `host.grants`, '' for none) may be neither read nor written, wherever it is: it is a secret,
    since an input that could edit it would grant itself anything.

    `grants` add to the policy, each only after `admitted` has checked it against the floor (the
    secrets, the store, the credentials, the layers, `code`, `trusted`, `interpreters`, the
    directories of `links`, and `key_envs`: each variable a model's key reads, to its endpoints), its
    path resolved: a read grant is a readable root, a write grant a writable root, an env grant a
    name on the allow-list. A write grant that is a directory outside the project gets the
    self-modification list and the `trusted` and `code` denies a root has; one on exactly a
    self-modifying path under a root lifts that deny. A grant left out is in `Policy.refused`."""
    floor = Floor(
        secrets=tuple(secrets),
        grants=store,
        credentials=tuple(str(Path(home, name)) for name in CREDENTIALS),
        layers=tuple(layers),
        code=tuple(code),
        trusted=tuple(trusted),
        interpreters=tuple(interpreters),
        links=tuple(str(PurePosixPath(link).parent) for link in links),
        key_envs=key_envs,
    )
    allowed, refused = admitted(grants, floor)
    given = [Path(g.target) for g in allowed.of(Kind.WRITE)]
    roots = [str(Path(root, w).resolve()) for w in config.write]
    # a granted directory beyond the project is a root of its own; one inside a root changes nothing
    # but its exact self-modifying path, below
    outside = [str(g) for g in given if g.is_dir() and not any(_within(str(g), r) for r in roots)]
    writable = [
        *roots,
        scratch,
        *([str(Path(memory).resolve())] if memory else []),
        *(str(g) for g in given),
    ]
    # A host import path *inside* a writable root is denied. One that *is* a root (the project
    # itself on sys.path, as under `python -m bh_02`) is not: denying it would make the project
    # read-only. What that leaves: a module an input writes at the project root could shadow one
    # the host has not imported yet. The `bh-02` console script never puts the root on sys.path.
    under = [p for p in host if p not in writable and any(p.startswith(r + "/") for r in writable)]
    lifted = {str(g) for g in given}
    selfmod = [
        denied
        for r in (*roots, *outside)
        for name in SELF_MODIFYING
        if (denied := str(Path(r, name))) not in lifted
    ]
    hidden = [
        *(str(Path(root, name).resolve()) for name in config.hide),
        *secrets,
        *([str(Path(store).resolve())] if store else []),
    ]
    # A secret an input may not read, it may not overwrite or remove either: one under a writable
    # root (a `hide`n file, a state directory) is denied writing too, or an input could replace
    # what it can't see.
    kept = [s for s in hidden if any(s == r or s.startswith(r + "/") for r in writable)]
    # bh-02's configuration under a writable root (bh-02 run from the home directory): an input
    # there could replace a file a later session reads on the host and trusts, the person's
    # startup file with a link to one the jail hides, say. Only strictly under one: a root that is
    # the directory or inside it (bh-02 run in its own config) would be left read-only.
    reach = (*roots, *outside)
    configured = [t for t in trusted if any(t.startswith(r + "/") for r in reach)]
    # bh-02's own code under a writable root (bh-02 working on its own checkout, an editable
    # install; or run from a home the checkout is in): an input there could write a module bh-02
    # imports later (a plugin a layer names, a module a reload imports), so it would choose code
    # bh-02 runs in its own process. By package, whatever `host` holds: a package an import
    # hook finds is on no `sys.path`, and a `src` that is the project itself is not denied there.
    # Only strictly under a root, as `trusted`: one the project is would leave it read-only.
    running = [c for c in code if any(c.startswith(r + "/") for r in reach)]
    # The interpreter bh-02 itself runs on, under a root an input may write (bh-02 run from a
    # directory that holds the uv-managed Python, the home directory say): the next bh-02 start on
    # the host would run what an input wrote there, outside any jail. `host` denies the standard
    # library and the venv's prefix, but in a venv layout the base's own binary is on neither (with
    # no venv the whole prefix is, and this adds nothing). Files only: a deny on a link is the mount
    # on what it leads to, so the file is what holds. Strictly under a root, as `host`.
    allows = tuple(writable)
    interpreter = [i for i in interpreters if i not in allows and any(i.startswith(r + "/") for r in allows)]
    # And the links on the way to it, which a mount on the file does not hold (the entry of a link
    # can be renamed, and an input plant its own interpreter at the name): their directories.
    holders = link_directories(links, allows)
    denies = [
        *layers,
        *under,
        *selfmod,
        *(str(Path(root, d).resolve()) for d in config.deny),
        *kept,
        *configured,
        *running,
        *interpreter,
        *holders,
    ]
    return Policy(
        # The program's socket is a channel brig reserves and binds into the jail (`jail`), so no
        # directory for it is named here.
        writable=allows,
        write_denies=tuple(denies),
        masks=(*(str(Path(home, name)) for name in CREDENTIALS), *hidden),
        env_allow=(
            *(BASELINE_ENV if config.env is None else config.env),
            *(g.target for g in allowed.of(Kind.ENV)),
        ),
        env_set=(("TMPDIR", scratch),),
        readable=tuple(g.target for g in allowed.of(Kind.READ)),
        refused=refused,
    )


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def admitted(grants: Grants, floor: Floor) -> tuple[Grants, tuple[str, ...]]:
    """`grants` that are not on `floor`, and the words for each that is (`grants.refusal`), in the
    order given. The path of a read or write grant is resolved first (`Path.resolve`), as are the
    floor's paths, so a link to a floor path is refused as the path it leads to; a granted path that
    resolves to `/`, or a read grant of a path that is not there, is left out too, with the reason.
    The admitted grant carries the resolved path: what the jail mounts is what was checked."""
    resolved = _resolved(floor)
    kept: list[Grant] = []
    refused: list[str] = []
    for grant in grants:
        try:
            each = _resolving(grant)
        except Invalid as error:
            refused.append(f"{grant} is never granted: it resolves to a path that can't be granted ({error})")
            continue
        if why := refusal(each, resolved):
            refused.append(why)
        elif each.kind is Kind.READ and not Path(each.target).exists():
            refused.append(f"{each} is not applied: there is nothing at {each.target} to read")
        else:
            kept.append(each)
    return Grants(tuple(kept)), tuple(refused)


def _resolving(grant: Grant) -> Grant:
    if grant.kind in (Kind.READ, Kind.WRITE):
        return Grant(grant.kind, str(Path(grant.target).resolve()))
    return grant


def _resolved(floor: Floor) -> Floor:
    def each(paths: Sequence[str]) -> tuple[str, ...]:
        return tuple(str(Path(p).resolve()) for p in paths)

    return replace(
        floor,
        secrets=each(floor.secrets),
        grants=str(Path(floor.grants).resolve()) if floor.grants else "",
        credentials=each(floor.credentials),
        layers=each(floor.layers),
        code=each(floor.code),
        trusted=each(floor.trusted),
        interpreters=each(floor.interpreters),
        links=each(floor.links),
    )


def link_directories(links: Sequence[str], writable: Sequence[str]) -> tuple[str, ...]:
    """The directories an input may not write, so that it cannot change a link on the way to the
    interpreter bh-02 runs on. `links` is that chain as the host found it (`facts.links_on_the_way`):
    where each link's own entry sits, absolute, in the directory that physically holds it.

    A mount on the interpreter's file holds the file, not the links that lead to it: the entry of
    a link in a writable directory can be renamed, and a Python of the input's own planted at its
    name (a project opened at the home directory holds uv's `cpython-3.15-<platform>` link to the
    versioned directory the venv's `python` goes through, and the next `uv run` on the host would
    execute what it planted). Only the directory that holds the link refuses that. So, for each
    link, its directory, when it lies strictly under a root in `writable` (the roots the jail may
    write; elsewhere an input changes nothing). Not a root itself, as for `host`: the project is
    the directory that holds the link, and denying it would leave the project read-only. Each once,
    in the order the links are met."""
    holders = (str(PurePosixPath(link).parent) for link in links)
    return tuple(dict.fromkeys(h for h in holders if any(h.startswith(r + "/") for r in writable)))


def allowlisted(policy: Policy, readable: Sequence[str]) -> Policy:
    """`policy`, reading by allowlist: `readable` is the tree an input may read (besides the policy's
    own, the read grants), and the policy's masks inside it become the carve-outs. A mask under no
    readable or writable root is dropped: nothing there is in the jail to keep from the input, and
    brig would mount one over a path that is there and so cap `fs_read` at best-effort for good (a
    mount the host can undo). The environment is the policy's, unchanged, and so are the writes but
    one kind: a path denied both reading and writing (a secret under the project) keeps only its
    mask. bubblewrap masks an existing one with a read-only `/dev/null`, which refuses writes and
    removal too (a write deny as well would be a bind of the real file, under the mask). An absent
    one has nothing to mask, so an input could create it; it is left alone: a directory there would
    be in the person's way, and nothing of bh-02's reads one."""
    roots = (*readable, *policy.readable, *policy.writable)
    masks = tuple(m for m in policy.masks if any(m == r or m.startswith(r.rstrip("/") + "/") for r in roots))
    return replace(
        policy,
        write_denies=tuple(d for d in policy.write_denies if d not in policy.masks),
        masks=masks,
        readable=(*readable, *policy.readable),
    )


def readable_roots(
    *,
    argv: Sequence[str],
    interpreter: Sequence[str],
    system: Sequence[str],
    code: Sequence[str] = (),
) -> tuple[str, ...]:
    """What a Linux jail reads besides what it may write: the system tree, the interpreter's
    trees (the standard library under `sys.base_prefix`, the environment under `sys.prefix`),
    the directory of every absolute path the command names (the worker program's own), and
    bh-02's own code (`code`: the directory of each package it runs, which the extensions'
    worker imports cordis from; with an editable install, the workspace's `src/cordis`, which
    the interpreter's trees don't hold). Not the host's whole `sys.path`: under pytest or
    `python -m` it holds the workspace root, and with it the whole workspace, for
    nothing a worker needs."""
    named = [str(Path(arg).parent) for arg in argv if arg.startswith("/")]
    return tuple(dict.fromkeys([*system, *interpreter, *named, *code]))


def told_reads(trees: Sequence[str], own: Sequence[str]) -> tuple[str, ...]:
    """The trees a jail reads, as the model is told them: each once, none that another of them
    holds (bh-02's own code, or the interpreter's environment, inside the project), the jail's
    own directories (its scratch and the program's socket, named anew at every start) as `$TMPDIR`
    alone, so the prompt is the same from one start to the next (the claude-code provider starts
    Claude Code again when it changes)."""
    kept = [t for t in trees if not any(t == o or t.startswith(o + "/") for o in own)]
    outer = [t for t in kept if not any(t.startswith(o + "/") for o in kept)]
    return (*dict.fromkeys(outer), "$TMPDIR")


def git_author(name: str, email: str) -> tuple[tuple[str, str], ...]:
    """The person's git identity as the variables git reads before any config file:
    `GIT_AUTHOR_*` and `GIT_COMMITTER_*`, for what is not empty. A Linux jail has no home
    directory, so a jailed `git commit` can't read `~/.gitconfig`; these carry the name and
    email alone, never the rest of the person's config (aliases, credential helpers, includes)."""
    pairs = [("NAME", name), ("EMAIL", email)]
    return tuple(
        (f"GIT_{who}_{what}", value) for who in ("AUTHOR", "COMMITTER") for what, value in pairs if value
    )


#: Where hosts keep sockets other programs listen on, as brig lists them (`SOCKET_DIRECTORIES`,
#: which it does not export): a jail that sees one is graded `network` violated, because a socket
#: it can dial can carry the network for it. `$XDG_RUNTIME_DIR` is one too (`socket_refusal`).
_SOCKET_PLACES: tuple[str, ...] = ("/run", "/var/run", "/tmp", "/var/tmp", "/dev/shm")


def socket_refusal(roots: Sequence[tuple[str, str]], runtime_dir: str) -> str:
    """Why a jail can't start with `roots` (each a what and an absolute, resolved path: the
    project, the scratch directory, ...), or "" when none is at or under a place where hosts keep
    sockets (`_SOCKET_PLACES`, `runtime_dir`: `$XDG_RUNTIME_DIR`, "" when unset). The message
    says why and what to do."""
    places = (*_SOCKET_PLACES, *([runtime_dir.rstrip("/")] if runtime_dir.startswith("/") else []))
    found = [
        (what, path, place)
        for what, path in roots
        for place in places
        if place and (path == place or path.startswith(place + "/"))
    ]
    if not found:
        return ""
    lines = "; ".join(f"{what} {path} is under {place}" for what, path, place in dict.fromkeys(found))
    return (
        f"the jail can't start: {lines}. That is where hosts keep sockets, and a jail that can "
        "see one can dial it, which reaches the network round the jail's proxy, so brig grades "
        "the network violated and bh-02 would not call it confined. Use a project and a state "
        "directory (`XDG_STATE_HOME`, where the jail's scratch and the project's memory are kept) "
        f"outside {', '.join(places)}, or run with `--no-jail`, which confines nothing"
    )
