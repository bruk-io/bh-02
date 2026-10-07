# tui-cordis-plugin

bh-02's ui: a Textual app bound as `input`, `output` (whose `confirm` asks about the model's code in a
modal) and `frame` by `tui:app`, and small rows that push into the app's frame: the status
bar's fields (`tui:status`: the session's id, the model, the jail's grades) and the palette's
commands (`tui:palette`). The screen is the conversation (the transcript over the composer),
the whole width, and the status bar along the bottom. Imports nothing from any other plugin;
the shapes are in `../../CONTRACTS.md`.

- **Value half** (no cordis): `app.py` (the `BhApp` and `running`, which runs it on the event loop
  cordis already runs), `ports.py` (`TuiInput`, `TuiOutput` and `Frame`, the values the ui binds as `input`,
  `output` and `frame`, and the `Bridge` they share with the app), `messages.py` (what they post), `render.py` (events as text or theme-styled
  `Content`, pure: markdown-ish prose, highlighted code, coloured diffs), `history.py` (the
  session's history file, and `replayable`, the pure choice of what to draw again),
  `frame.py` (the usage and model fields and the palette's entries, pure), `status.py` (what
  the frame's rows need, and `ModelField`), `theme.py` (the themes the app registers),
  `bh01_theme.py` (every colour: generated, never edited), `tokens.py` (bh-01's token CSS to
  that module's source, pure), `widgets/` (one module per widget: `Transcript`, `Composer`,
  `StatusBar`, `ApprovalScreen`, and the palette's `CommandsProvider`).
- **`wiring.py`**: the rows. `tui:app` depends on its config alone, so no reload elsewhere
  restarts the app and loses the transcript.

The input, output and frame never touch a widget: cordis's coroutines run outside the app's task, so they post a
message and the app draws it. Whatever ends the app (Ctrl-Q, `/exit`, `/quit`, a crash) ends
the bridge: a pending `read()` returns None (a crash: raises `AppCrashed`, which reaches the
command line through the chat row's `done`), turns waiting on Ctrl-C return, questions are a no.
Ctrl-C is a priority binding that interrupts the running turn and never quits; one pressed
after a line is sent and before its turn listens (or during a slash command) is held for the
turn, and the next read drops it. `confirm()` comes from plain coroutines (not Textual
workers), so the modal is `push_screen` with a callback resolving a future. Questions are
shown one at a time, the rest queued; an interrupted turn cancels its future and its modal
comes down wherever it is (anything shown over it is popped first); Ctrl-C with a question up
answers every open one no and interrupts the turn. No palette opens over a question. A
question just shown answers nothing for 0.4 s (`GRACE`; `BhApp(grace=...)`), its keys line
dimmed meanwhile: a person typing when it comes up ("Run n...") must not decline it with the
`n`. Those keys are dropped, not handed to the composer: the modal holds focus, and a message
half-typed around a question is less surprising cut short than finished with stray letters.
Ctrl-C still stops the turn at once.

The frame. `tui:palette` pushes the `commands` broker's `specs` method itself, which the
palette (Ctrl-P) calls each time it opens, so a command registered
after the push is offered with no reload; choosing one sends `/name` through the input as if
typed, or puts `/name ` in the composer when it takes arguments; a spec's `choices` (read each
time it opens too) are entries of their own that run at once (`/model haiku`, one per model).
`/help` and `/exit` are the ui's own entries. `tui:status` shows the running session's id (from
the `sessions` value, `(resumed)` after it on a resume) and the kernel's jail grades (and, as a note in the conversation each time a kernel comes up, what its jail says the person should know: `kernel.notice()`), and asks
the `models` value which model the model row names now and on which provider (`models.current()`;
`config.model_row`, `model`, names the row whose lifecycle it follows): `sonnet (claude-code)`
(narrow: `sonnet`). It observes lifecycle events to show it again at each of that row's events:
`sonnet (claude-code, starting…)` (narrow: `sonnet…`) from the row's unloading until it is active again, so a
`/model` or `/clear` shows the new model at once and that it is still starting (the Claude
CLI takes seconds); its first push reads the row's state from the loader's `status()`. The
output's lifecycle tells the bridge which rows are coming up, so a line typed while nobody
reads says `⧗ waiting for loop to start; ...` and is read once it is up. A command's
`restarting` event (`/model`, `/clear`) makes the bridge hold every line, even from the chat
row still reading, until the rows it names are active again, so a line typed right after the
command waits for the new model and says so. The `usage` field is the output's own: the session's running totals of usage
events (each event is one turn's usage, so they sum), starting from what the session's history
already holds, so a resumed session's field counts its earlier runs too.

`running` puts the loop's task factory back once the app is up (Textual makes it eager at
start, and the event loop is cordis's too). The theme is registered in `App.__init__` and every
custom `$bh-*` token has a default in `get_theme_variable_defaults` (a test checks), since a
real launch parses every stylesheet at startup and `run_test()` does not.

**Streaming.** The output posts a turn's events in batches, never faster than the app draws
them (`Shown` carries a future the app settles once drawn; the next batch gathers meanwhile,
and reading waits once it is large), and gives the loop a turn after every event, so a reply
that yields everything at once still leaves Ctrl-C heard mid-reply. The app joins each run of
streamed text before drawing and recording it.

**The transcript** draws a turn as it streams: a block per event, a CSS class per kind. Text
and thinking grow one `Stream`, which settles its text into pieces of a couple of dozen lines
and re-draws only the open one, so a chunk costs the same at line 2,000 as at line 1 (a Pilot
test times it). Text with no newlines settles by size: a piece longer than 2,000 characters is
cut at its last line end or space, which ends a line there on screen (a paragraph that long is
drawn as two), so a long paragraph costs the same at its end as at its start too. Thinking folds to one line once the reply moves on. A result or a call hangs
beside its marker and an input's code has a left border, so wrapped lines keep their gutter.

**History.** With `history` in its config (a session's layer sets `{"history":
"<session>/events.jsonl"}`), the app appends every entry the transcript draws to that file
(JSON lines: the events, streamed runs joined, and the ui's own `user`, `turn_end` and
`noted`), and the row draws
its last `replay` entries (400; a streamed run counts as one) again when it starts. Once the
file holds more than twice `replay` entries it is trimmed as the row starts (a temporary file,
then a rename) to a `carried` entry (how many were trimmed, and the usage they added up to)
and the last `replay`, so it never grows without bound; a trim that fails leaves the file
whole, removes its temporary file and says so in the transcript. `/clear` reaches the ui as a
`cleared` event: the transcript drops every block and the note that follows is all it shows,
with any line typed after `/clear` that is still waiting to be read (it is drawn again);
the file records `cleared` like any event, and a replay starts after the last one, while the
usage before it still counts (the session's totals). A session made before `cleared` existed
also empties the file underneath the app; the next write then puts a `carried` entry first for
what was forgotten, so the usage a resume adds up is the usage shown live. The file is the ui's own; the row still
depends on its config alone.

**The look is bh-01's.** `scripts/sync-tokens` copies bh-01's `dist/tokens/colors.css` and
`dist/themes/default.css` into `bh-01-tokens/` (a snapshot, so the tests need no bh-01
checkout) and writes `bh01_theme.py` from it: `bh-01-dark` (the default) and `bh-01-light`,
Textual's fields mapped from bh-01's roles (`tokens.THEME_FIELDS`), and every
`--bh-color-<role>` as `$bh-<role>` (`$bh-text-muted`, `$bh-border`, `$bh-primary-glow`, ...;
`rgba()` becomes `#RRGGBBAA`). `scripts/sync-tokens --check` fails when either is stale
(`scripts/check` runs it when bh-01 is checked out beside this repository, and says it skipped
otherwise), and a test fails when the committed module is not what the snapshot generates. A widget's CSS names
roles, never colours; mandarin (`$bh-primary`, `$bh-ring`) is for what can be acted on or is
selected. Every stylesheet is parsed against each theme in a test, as a real launch does.

The status bar shows its fields in a fixed order (session, model, jail, usage,
then any other). Each field is pushed with its shorter forms (`frame.status(field, text,
*shorter)`: the status row's short form of the session id, `frame.usage_forms`, `render.jail_forms`), so the bar
never parses text back. When they don't fit it gives up room a step at a time: narrower
separators, the session as its id's last part (`↻` marks a resumed one: `b1c2 ↻`; `--resume`
takes it), usage in short (`12k/678 $0.12`), the jail's axes by their initials (`jailed w✓ n✓
r✓ e✓`, then `w✓n✓r✓e✓`), its grades as glyphs alone (`jailed ✓✓✓✓`, in the order fs_write,
network, fs_read, env). Once the line fits, each field gets back the fullest form that still
fits, the session's first, so a step a later one made needless is undone. Only when the
shortest forms don't fit is the widest field cut at a word's end with `…`, then fields dropped
(any other, session, model, usage). The jail's field is never cut or dropped. Muted text in the frame (the bar, the usage chip,
the modal's keys) is `$bh-text 70%`, not bh-01's `text-muted`, which
measures about 2.2 to 2.6:1 on these surfaces; 70% is 5.2:1 or better in both themes. The
approval modal's background is translucent, so the conversation shows through around it; its
code is highlighted as the transcript's is (`render.code`, in theme tokens).
