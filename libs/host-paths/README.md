# host-paths

Paths as bh-02's own process must judge them when the model can write some of them. bh-02 reads
some files on the host and trusts them: the models file, the person's startup file, memory files
outside the project. Each is read there only when nothing the model can write chooses what is
read, and every package that makes that call must make it the same way. bh-02 also writes in one
directory the model can write, its auto memory: the same rule, for a write. bh-02's plugins may
import nothing of each other's, so the one definition lives here.

| Name | What it is |
|---|---|
| `config_home(environ, home)` | `$XDG_CONFIG_HOME`, else `home/.config`; a relative value counts as unset, as the XDG spec says |
| `state_home(environ, home)` | `$XDG_STATE_HOME`, else `home/.local/state`; the same rule |
| `walked(path)` | every place reading an absolute path goes through: each directory and link on the way, a link where it sits and then where it leads, then where it ends; `..` after the links before it, as the kernel's lookup does |
| `MOST_LINKS` | how many links one walk follows (40, Linux's limit), so a loop ends |
| `roots(root)` | a root as named and as it resolves |
| `passes(path, roots)` | the places reading `path` goes through that are under one of the roots: a link the model could repoint, a directory it could swap for one |
| `directory_beneath(root, names)` | the directory `names` reaches beneath `root` (a path or a descriptor), opened a name at a time through no link: its descriptor, closed on leaving |
| `read_beneath(root, names, cap=)` | the bytes of the file `names` reaches beneath `root`, walked to the same way and read from the descriptor it was opened as; or `Link(target)` when the last name is a link, not followed |
| `write_beneath(root, names, data)` | write `data` as the file `names` reaches beneath `root`, walked to the same way, made whole under a name of its own and moved over the name; True when it replaced a file. A link or a second name at the name is refused, never followed or replaced |
| `remove_beneath(root, names)` | remove that file, refusing a link or a second name the same way |
| `Appender(path, new=)` | one file appended to off the event loop: `append(data)` queues bytes and returns (no running loop needed), a thread writes them in the order queued, `await flush()` waits for the last, `await close()` for the last and then closes the file. Opened for append through no link, made 0600; with `new` the file must not be there. A write that fails is raised by every `append`, `flush` and `close` after it, and nothing queued after it is written. The thread checks before each write that the file at the path is still the one the appender means (the one it holds open, or the one found when it was made): a file renamed over, removed or turned into a link is refused as `Replaced` (an `OSError`), never written to the old inode or to another conversation's file. `Appender.open(path)` opens at once instead of at the first write |
| `Linked`, `NotOneFile`, `TooLarge` | the OSErrors the walk, the read, the write and the removal raise: a name is a link (`part`: a directory on the way, or the file written or removed); not a regular file with one name (`mode`, `names`); over the cap |

The opener is for a file the model may have written that bh-02 reads on the host: memory files
in the project, the project's `.git/HEAD`, the model's extensions. Each flag is there for a
reason (the module's docstring says which): `O_NOFOLLOW` on every name, `O_DIRECTORY` on the way,
`O_NONBLOCK` so a FIFO is never waited on, `O_CLOEXEC` on every descriptor and `O_NOCTTY` on the
file; then the file is judged by its descriptor, never its name again: a regular file with one
name (a hard link, or a file removed since, is not), no larger than the caller's cap, read to at
most the cap. The caller decodes the bytes and decides what a final link means.

The writer is for the one directory the model can write that bh-02 writes in too: the auto memory
directory. It walks as the opener does, judges the name as it stands (a link, a second name or
anything but a regular file is refused and left alone), makes the file under a random name beside
it (`O_CREAT | O_EXCL | O_NOFOLLOW`, by descriptor) and renames it over the name. The rename
replaces whatever the name is by then and follows nothing, so a link the model plants after the
check is replaced and no write reaches past the directory, and a reader sees the old file or the
new one, never half of it.

The appender is for the files bh-02 keeps for the person and writes as a session goes on (a conversation's transcript, a sub-agent's event log), which must never be written on the event loop the TUI shares or in a mode the umask chose. `O_APPEND` keeps each write at the end, `O_NOFOLLOW` refuses a link at the name, `O_CREAT` at 0600 makes the file in the one call that opens it, and one worker thread writes in the order queued, so a write is never overtaken or mixed with another, and a caller that is cancelled leaves its write to finish. A failed write is kept and raised rather than lost: the transcript is the conversation, and a file with a hole in it would resume as another one. A held descriptor stays on the inode it opened, so a file `/clear` or `/compact` replaced by rename would take the old conversation's next lines into a file nobody reads (or, opened late, into the new conversation's): the check against the path before each write turns that into `Replaced`.

It depends on the standard library alone and knows nothing of cordis or bh-02. Its gate is in
`pyproject.toml`; the functions that read the filesystem are named in its purity budget,
since reading links is what they are for, and so is the opener.
