"""The sealed test set: seeds nobody can build without a key kept outside the repository.

A family's open seeds are 0, 1, 2 and so on, for building, tuning and piloting. Its sealed seeds
come from HMAC-SHA256 of the key, the family, a set number and an index. The repository holds only
the key's SHA-256 (`scenarios/seal.json`), committed before any sealed world is built, and a ledger
(`results/sealed-ledger.jsonl`) gets a line whenever a sealed set is built or run. A sealed run
takes the lowest set no run has used, so each set is run once, with every setting to compare in
that one run; it is refused while the envelope code has uncommitted changes, since its version
would name code that was not what ran. SCENARIOS.md says why.

The decisions are pure (`sealed_seeds`, `decide_run`); `init`, `load_key`, `build` and `begin_run`
read and write the key, the commitment and the ledger, at the paths they are given.
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_LAB = Path(__file__).resolve().parent.parent
COMMITMENT = _LAB / "scenarios" / "seal.json"
LEDGER = _LAB / "results" / "sealed-ledger.jsonl"
ENV = "TOOL_OUTPUT_LAB_SEAL_KEY"  # the key in hex, in place of the key file
VERSIONED = ("compressors", "claude_code/hook.py")  # the envelope code a run's version names
_KEY_BYTES = 32


class SealError(Exception):
    """The seal cannot do what was asked; the message says what to do instead."""


@dataclass(frozen=True)
class Entry:
    """A line of the ledger: the key made (keyed), a sealed set built (built), or run (run)."""

    date: str
    event: str
    family: str = ""
    set_no: int = -1
    version: str = ""
    note: str = ""


# --- the decisions -------------------------------------------------------------------------------


def commitment(key: bytes) -> str:
    """What the repository holds of the key: its SHA-256."""
    return hashlib.sha256(key).hexdigest()


def open_seeds(n: int) -> tuple[int, ...]:
    return tuple(range(n))


def sealed_seeds(key: bytes, family: str, set_no: int, n: int) -> tuple[int, ...]:
    """The first `n` seeds of a family's sealed set, 64 bits each, from the key."""
    return tuple(
        int.from_bytes(hmac.digest(key, f"{family}:{set_no}:{i}".encode(), "sha256")[:8], "big")
        for i in range(n)
    )


def spent(entries: Iterable[Entry], family: str) -> frozenset[int]:
    """The sets of a family that a run has used."""
    return frozenset(e.set_no for e in entries if e.event == "run" and e.family == family)


def decide_run(entries: Iterable[Entry], family: str, dirty: tuple[str, ...]) -> int:
    """The set a sealed run of `family` takes: the lowest one no run has used.

    Raises:
        SealError: the envelope code has uncommitted changes, so the run's version would not name
            the code that ran.
    """
    if dirty:
        raise SealError(
            f"the envelope code has uncommitted changes ({', '.join(dirty)}): commit them first, so the"
            " ledger's version names the code this run tests"
        )
    used = spent(entries, family)
    return next(n for n in range(len(used) + 1) if n not in used)


def key_from(text: str) -> bytes:
    """A key written as hex, from the key file or the environment.

    Raises:
        SealError: the text is not 32 bytes of hex.
    """
    try:
        key = bytes.fromhex(text.strip())
    except ValueError:
        key = b""
    if len(key) != _KEY_BYTES:
        raise SealError(f"a seal key is {_KEY_BYTES} bytes written as {_KEY_BYTES * 2} hex characters")
    return key


# --- reading and writing -------------------------------------------------------------------------


def key_path(environ: Mapping[str, str]) -> Path:
    """Where the key lives: the XDG config directory, outside the repository."""
    base = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "tool-output-lab" / "seal.key"


def read_ledger(ledger: Path) -> list[Entry]:
    if not ledger.exists():
        return []
    return [Entry(**json.loads(line)) for line in ledger.read_text(encoding="utf-8").splitlines() if line]


def _append(ledger: Path, entry: Entry) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def committed(commitment_file: Path) -> str | None:
    if not commitment_file.exists():
        return None
    return str(json.loads(commitment_file.read_text(encoding="utf-8"))["sha256"])


def init(key_file: Path, commitment_file: Path, ledger: Path, rekey: bool = False) -> str:
    """Make a key, keep it outside the repository, and commit its SHA-256 in it.

    Raises:
        SealError: a key is committed already (pass `rekey` to replace it), or a sealed run has
            used the committed key, whose tasks a new key could not rebuild.
    """
    old = committed(commitment_file)
    if old is not None and not rekey:
        raise SealError(f"a key is committed already ({old[:12]}...): check it with `./lab seal verify`")
    if old is not None and any(e.event == "run" for e in read_ledger(ledger)):
        raise SealError("a sealed run has used the committed key: keep that key, since its tasks need it")
    key = secrets.token_bytes(_KEY_BYTES)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex() + "\n")
    digest = commitment(key)
    commitment_file.write_text(
        json.dumps({"sha256": digest, "created": _now()}, indent=2) + "\n", encoding="utf-8"
    )
    _append(ledger, Entry(_now(), "keyed", note=f"replaces {old[:12]}" if old else ""))
    return digest


def load_key(environ: Mapping[str, str], key_file: Path, commitment_file: Path) -> bytes:
    """The key, from the environment or the key file, checked against the committed SHA-256.

    Raises:
        SealError: no key is committed, none is on this machine, or it is not the committed one.
    """
    expected = committed(commitment_file)
    if expected is None:
        raise SealError("no key is committed: make one with `./lab seal init`")
    if ENV in environ:
        key = key_from(environ[ENV])
    elif key_file.exists():
        key = key_from(key_file.read_text(encoding="utf-8"))
    else:
        raise SealError(f"no seal key on this machine: put it in {key_file} or in {ENV}")
    if commitment(key) != expected:
        raise SealError(
            f"this key is not the committed one ({expected[:12]}...): find the key it was made from"
        )
    return key


def version(lab: Path = _LAB) -> tuple[str, tuple[str, ...]]:
    """The envelope code's version (a hash of its committed git trees) and the paths with uncommitted
    changes.

    Raises:
        SealError: git cannot read the lab's history.
    """
    try:
        trees = [
            subprocess.run(
                ["git", "rev-parse", f"HEAD:./{p}"], cwd=lab, check=True, capture_output=True, text=True
            ).stdout.strip()
            for p in VERSIONED
        ]
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", *VERSIONED],
            cwd=lab,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise SealError(
            f"git cannot read the lab's history ({e}): run from a checkout of the repository"
        ) from e
    dirty = tuple(line[3:] for line in status.splitlines() if line.strip())
    return hashlib.sha256(" ".join(trees).encode()).hexdigest()[:16], dirty


def build(key: bytes, family: str, set_no: int, n: int, ledger: Path, note: str = "") -> tuple[int, ...]:
    """A sealed set's seeds, leaving a line in the ledger that they were built."""
    _append(ledger, Entry(_now(), "built", family, set_no, note=note))
    return sealed_seeds(key, family, set_no, n)


def begin_run(
    key: bytes, family: str, n: int, ledger: Path, code: tuple[str, tuple[str, ...]], note: str = ""
) -> tuple[int, tuple[int, ...]]:
    """Start a sealed run: take the lowest unused set, record it as used, and give its seeds.

    `code` is `version()`: the envelope code's version and its uncommitted paths. With uncommitted
    paths, `decide_run`'s SealError comes through and nothing is recorded.
    """
    ver, dirty = code
    set_no = decide_run(read_ledger(ledger), family, dirty)
    _append(ledger, Entry(_now(), "run", family, set_no, ver, note))
    return set_no, sealed_seeds(key, family, set_no, n)


# --- ./lab seal ----------------------------------------------------------------------------------


def _status(environ: Mapping[str, str], key_file: Path, commitment_file: Path, ledger: Path) -> str:
    expected = committed(commitment_file)
    lines = [f"commitment: {expected[:12] + '...' if expected else 'none (./lab seal init)'}"]
    try:
        load_key(environ, key_file, commitment_file)
        lines.append("key: on this machine, and it is the committed one")
    except SealError as e:
        lines.append(f"key: {e}")
    entries = read_ledger(ledger)
    for family in sorted({e.family for e in entries if e.family}):
        built = sorted({e.set_no for e in entries if e.event == "built" and e.family == family})
        used = sorted(spent(entries, family))
        lines.append(f"{family}: sets built {built or 'none'}, sets run {used or 'none'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="./lab seal", description="The sealed test set (SCENARIOS.md).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init_p = sub.add_parser("init", help="make a key outside the repository and commit its SHA-256")
    init_p.add_argument("--rekey", action="store_true", help="replace a committed key no sealed run has used")
    sub.add_parser("verify", help="check that the key on this machine is the committed one")
    sub.add_parser("status", help="the commitment, the key, and each family's sets built and run")
    ns = parser.parse_args(argv)
    environ, key_file = os.environ, key_path(os.environ)
    try:
        match ns.cmd:
            case "init":
                digest = init(key_file, COMMITMENT, LEDGER, rekey=ns.rekey)
                print(f"key written to {key_file}, readable by its owner only")
                print(f"its SHA-256 {digest[:12]}... is in {COMMITMENT}: commit that file now")
                print("Keep a copy of the key file somewhere that outlives this machine.")
            case "verify":
                load_key(environ, key_file, COMMITMENT)
                print("the key on this machine is the committed one")
            case _:
                print(_status(environ, key_file, COMMITMENT, LEDGER))
    except SealError as e:
        print(f"seal: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
