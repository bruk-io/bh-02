# Open review findings for TASK-0046 (not yet addressed)

From the workflow's two review lenses (acceptance, cordis). Delete this file once each is fixed or answered.

## [minor] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/client.py

Criterion 2 says "each file is readable inside the jail". On Linux that is true of the content, not the file. The host sends the person's file as source text, but the path itself does not exist in the jail. `instructions()` still names that absolute path to the model ("the person may keep helpers of their own in <path>"), and the same prompt says nothing outside `reads()` exists. A model that tries to open the file to see the helpers fails. A helper that reads a file next to it (for example a `notes.md` in `~/.config/bh-02`) also fails, and `__file__` is not set. The design is deliberate and documented in both READMEs, but the implementer's list of deviations does not mention it.

Evidence: Probe in a real bubblewrap jail (installed `bubblewrap`; scratchpad wf-review/probe4.py). It ran `os.path.exists(person)`, `inspect.getsource(show)` and `NOTES`. Output: `(…/home/.config/bh-02/kernel.py ran first and defined: NOTES, pathlib, show. .bh-02/kernel.py ran next and defined: TOOLS)` then `False`, the source of `show`, `None`, `'<2>'`. So the helper runs, `getsource` works through linecache, the file does not exist in the jail, and `__file__` is absent. The repo's own Linux test asserts the same thing: test_python_repl.py `assert out.endswith("\nFalse\n'<2>'")`.

Suggested: Either list this as a deviation from criterion 2 and tell the model how to see the person's helpers (`inspect.getsource(name)`, not `open(path)`) when the jail reads by allowlist, or make the file readable in the jail as a read-only bind of that one file.

## [minor] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/client.py

A startup file that ends the worker (`os._exit`, a native crash, an OOM kill) locks out every later input, and the message never names the file. `_fresh` is cleared only after `_opening()` returns (line 339). When the startup input kills the worker, `_exchange` raises ConnectionError, so the next input starts a new worker, runs the same file again and dies again. Every input reads "the REPL's process ended during this input". A file that hangs behaves the same way: after Ctrl-C, `_fresh` is still True, so the next input runs it again. The project's file already did this before the change. The person's file now applies to every project, and it is the one the model is told not to edit and, on Linux, cannot see.

Evidence: Scratchpad wf-review/probe1.py, person's file `import os\nos._exit(3)\n` under a Confined jail. Inputs '1', '2' and '3' each returned exactly: `the REPL's process ended during this input; a new one starts with the next`. No input names the startup file and none ran.

Suggested: Clear `_fresh` before running the startup files, or catch ConnectionError per file in `_opening` and add a note naming the file ("<file> ended the REPL"). Then the next worker skips that file, or at least says which one did it.

## [minor] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/client.py

The "defined" list compares objects by identity (`_bh_before[n] is not v`, line 159), so it can leave out names a file defines. A rerun after an interrupted startup reports only the names whose objects changed. When both files bind a name to the same cached object (`WIDTH = 80` in each), the second file's note omits it. The list is also the last line of the file's output, so a file whose output has no trailing newline merges into it (this part is older than the change).

Evidence: probe1.py: Ctrl-C during the person's file (`import time; A = 1; time.sleep(3); B = 2`), then the next input. It reported `(…/kernel.py ran first and defined: B. .bh-02/kernel.py ran next and defined: C)`, while globals held `['time', 'A', 'B', 'C']`. A person's file `print('hello', end='')\nA = 1` gave `ran first and defined: helloA`.

Suggested: Track the names the exec bound (for example, run the file in a dict that records its writes, or compare against a fresh copy on reruns), and print the names on a line of their own with a leading newline or a sentinel.

## [minor] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/client.py

`startup` is not validated. A layer typo such as `startup = [".bh-02/kernel.py", 1]` makes `instructions()`, which runs on every request (lines 272 to 277, through `_placed` at line 185), raise a bare AttributeError instead of an error in the house style that says what to fix. The "startup files could not be looked at" path in `_opening` has no test.

Evidence: probe5.py with `KernelConfig(startup=[".bh-02/kernel.py", 1])`: `instructions raised AttributeError 'int' object has no attribute 'startswith'`, and the first input returned `(the startup files could not be looked at ('int' object has no attribute 'startswith'), so none ran)\n1`. `grep "could not be looked at" tests/` finds nothing.

Suggested: Add a `__post_init__` on KernelConfig that rejects anything but a str or a sequence of str. The error should name the row and say what to write (for example: `kernel: config startup must be a file name or a list of them, e.g. ["$XDG_CONFIG_HOME/bh-02/kernel.py", ".bh-02/kernel.py"]`).

## [minor] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/client.py

A startup file saved with a UTF-8 BOM fails with a SyntaxError, though `python file.py` runs it. Both the host read (line 431) and the worker read (line 149) use encoding 'utf-8', not 'utf-8-sig'. The project's file already behaved this way. The person's file, often edited with desktop tools, now shares it.

Evidence: probe1.py, person's file bytes `\xef\xbb\xbfA = 1\n` gave: `(…/kernel.py ran first and failed, so what it defines is missing:\nSyntaxError: invalid non-printable character U+FEFF (kernel.py, line 1))`.

Suggested: Read with encoding='utf-8-sig' in both places.

## [blocker] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/client.py

The host reads the person's startup file whenever its path doesn't touch the current project (client.py:420-437), but the jail never protects that file from writes. In a session run from the home directory (a case this change supports and tests), the home is a writable root and `$XDG_CONFIG_HOME/bh-02/kernel.py` is not write-denied (brig jail.py:184 denies layer files, self-modify names and secrets only). That session's model can replace the file with a link to a file the jail hides. Any later session in another project then follows the link on the host, reads the hidden file, and puts its whole text in the worker's linecache (client.py:144). The model can read it there, and a failing exec also prints the offending line in the first input's note, which is sent to the model provider without being asked. This breaks the guarantee the change adds to bh-02/CLAUDE.md (never read on the host a file the model can write, or reach through a link it could make, and hand its text to the model). The walk only checks the current project, so the same gap applies to any extra writable root the person sets in `BrigConfig.write`. The context and models plugins have the same cross-session gap for `~/.config/bh-02`, but before this change the kernel read nothing on the host.

Evidence: Repro script /tmp/claude-0/-home-user-bh-02/4dc0d93e-ad1a-579e-8549-da59b471193d/scratchpad/repro/cross_session.py, run with the worktree's .venv. Session A: spec_for(root=home) reports `write-denied covers the person's startup file: False`. A then links ~/.config/bh-02/kernel.py to ~/.ssh/id_ed25519. Session B runs in another project, with a jail that hides ~/.ssh. In B, `open(key)` raises `PermissionError: the jail hides it`, yet `''.join(linecache.getlines('<home>/.config/bh-02/kernel.py'))` returns `'-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n'`. A second run (token_case.py) puts a token-shaped line in the hidden file. B's first input `1` then comes back as `(... kernel.py ran first and failed ...\n  File ".../kernel.py", line 1, in <module>\n    CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-FAKEnotreal-XyZ\n ... NameError: name 'sk' is not defined ...)\n1`.

Suggested: Make sure no jailed input can ever write a file the host later reads. Write-deny the person's startup file(s) (best: `$XDG_CONFIG_HOME/bh-02/` as a whole, which also covers models.toml and context.toml) whenever they fall under one of the jail's writable roots. Do it as the layer files already are: add them to the paths the `layers` value hands to brig's `write_denies`. Then add a test where a home-rooted brig spec denies writing ~/.config/bh-02/kernel.py. Until that lands, `_ready` should not host-read a person's file whose way contains a link, unless every link on the way sits outside every writable root the jail grants.

## [minor] bh-02/plugins/brig-cordis-plugin/tests/test_jail.py

The new default `startup` includes `$XDG_CONFIG_HOME/bh-02/kernel.py`. The brig plugin's tests start a real `Kernel` in a subprocess with the developer's environment, and the brig plugin has no conftest that isolates XDG_CONFIG_HOME (the kernel and app tests got one). So on a Linux machine with bwrap, a developer who keeps their own startup file gets the startup note printed before `started`, and the test fails.

Evidence: With XDG_CONFIG_HOME pointing at a directory holding bh-02/kernel.py (`def show(x): return x`), test_a_killed_bh_02_s_jail_ends_with_it_and_the_next_jail_removes_what_it_left fails at test_jail.py:516: `assert b'started' in b'(/tmp/.../devconfig/bh-02/kernel.py ran first and defined: show)\n'`.

Suggested: Give bh-02/plugins/brig-cordis-plugin/tests a conftest like the kernel plugin's, pointing XDG_CONFIG_HOME at an empty directory of its own. Or pass `KernelConfig(root=..., startup=())` in the script `_KILLED_WITH_A_BACKGROUND_INPUT`.
