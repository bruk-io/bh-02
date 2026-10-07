# Open review findings for TASK-0049 (not yet addressed)

From the workflow's two review lenses (acceptance, cordis). Delete this file once each is fixed or answered.

## [minor] bh-02/plugins/context-cordis-plugin/src/context_cordis_plugin/touch.py

After a resume or a row reload, a rule or guidance file cut back to a leading prefix that ends at a paragraph break still counts as already told, so it is not told again. The model keeps believing the paragraph that was removed. The implementer reported this case as a deviation, and it only happens when the file changes across a resume or reload. Within one row's lifetime, a change is checked against the snapshot taken before the row told anything, so it is caught.

Evidence: `_told_in` (touch.py:54-59) tests `f"\n\n{text}\n\n" in result`, and the old note still contains the trimmed text followed by a blank line. Probe /tmp/claude-0/-home-user-bh-02/4dc0d93e-ad1a-579e-8549-da59b471193d/scratchpad/wf-review/probe2.py: transcript tool entry `6\n\nFrom .claude/rules/db.md, a rule for src/db/**:\n\nMigrations by hand.\n\nNever touch prod.`, and system now says `...:\n\nMigrations by hand.`. Output: `trimmed rule after resume told: ''`.

Suggested: Leave it as the documented limitation, or check that the text after the match begins a new note: the next `From ` header, a `(` error or shell note, the `\n... [N more chars` marker, or the end of the entry, instead of any paragraph.

## [minor] bh-02/CLAUDE.md

The new sentence says that both memory rows read the transcript's `messages` "once, at their first input". On-touch reads it at the first input that opens a file, not at its first input. CONTRACTS.md has it right ("at the first input that may need them"), and so do the context README and OnTouch's docstring.

Evidence: bh-02/CLAUDE.md:112 reads "read its `messages` once, at their first input". touch.py:85-89 returns '' for an input with no `touched` before it reads `self._transcript.messages`. The unit test asserts `told({"code": "1"}) == "" and transcript.reads == 0`.

Suggested: Say "at the first input that needs them (on-touch: the first that opens a file)", matching CONTRACTS.md.

## [minor] bh-02/plugins/kernel-cordis-plugin/src/kernel_cordis_plugin/python.py

The pattern that finds told shell notes (`_HINTED`, python.py:181-185) has two lazy `[^\n]*?` groups split by a fixed literal, so its time grows with the square of the line length. The model's code controls a tool result. The worker caps output at 20,000 chars, but the worker is the model's own process, and the host reads lines up to 1 MiB (client.py:40). A crafted result therefore stalls `_hinted` in bh-02's process. That happens at the shell-hints row's first input after a resume or reload, inside the memory worker thread, which the loop awaits and a stop waits on. This is a stall, not a breach of the read/run/credential boundary.

Evidence: Timed with `uv run python -B` on a scratch script that runs `_HINTED.findall('\n\n(this input ran ' + (A + B) * n + 'x')`, where A is the ' through a shell. ... next input: ' literal and B is '. Keep subprocess ... builds.)'. Results: n=300 (49 KB) 0.09 s; n=1000 (165 KB) 1.15 s; n=3000 (495 KB) 10.8 s. The growth is quadratic, so about 40 s per 1 MB entry, paid once for each such entry in the transcript.

Suggested: Use a linear pattern to find each note line, e.g. `\n\n(\(this input ran [^\n]*)(?=\n\n|\Z)`. Then take the ways out with `str.partition` on the 'next input: ' literal and `str.removesuffix` on the closing literal (both from `_HINT`), so nothing in the scan backtracks.

## [minor] bh-02/CONTRACTS.md

CONTRACTS.md (transcript row), the context and agent READMEs, `_told_in`'s docstring (touch.py:56-58) and the two new tests' docstrings all say a note counts as told when a `tool` entry holds it 'after its result', and not when 'a result is one (an input printed it)'. The code can't tell where the result ends and the notes begin. Any text that follows a blank line anywhere in the entry counts, including inside what the input printed. Only a result that begins with the note is excluded. The behaviour is defensible, since the model did see that text, but the documented rule is stricter than the code.

Evidence: A scratch run with `ShellHints(T({'role':'tool','content': f'header\n\n{shell_note((("cat","read"),))}\n\nmore output'}))({'code': "import subprocess; subprocess.run(['cat','x'])"})` returns '', and `OnTouch(S(), T({'role':'tool','content':'printed\n\nFrom a.md:\n\nA.\n\nmore printed'}))({'touched': ('/p/x',)})`, where S says ('/p/a.md', 'From a.md:\n\nA.'), also returns ''. Both notes appeared only inside printed output, yet both are treated as already told.

Suggested: Reword the docs and docstrings to say what the code does: a note counts as told when it appears whole after a blank line anywhere in a `tool` entry, except at its start. Alternatively, have the loop mark where the result ends, if the stricter rule is wanted.
