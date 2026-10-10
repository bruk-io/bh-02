# host-paths

Paths as bh-02's own process must judge them when the model can write some of them. bh-02 reads
some files on the host and trusts them: the models file, the person's startup file, memory files
outside the project. Each is read there only when nothing the model can write chooses what is
read, and every package that makes that call must make it the same way. bh-02's plugins may
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
| `Linked`, `NotOneFile`, `TooLarge` | the OSErrors the walk and the read raise: a directory on the way is a link (`part`); not a regular file with one name (`mode`, `names`); over the cap |

The opener is for a file the model may have written that bh-02 reads on the host: memory files
in the project, the project's `.git/HEAD`, the model's extensions. Each flag is there for a
reason (the module's docstring says which): `O_NOFOLLOW` on every name, `O_DIRECTORY` on the way,
`O_NONBLOCK` so a FIFO is never waited on, `O_CLOEXEC` on every descriptor and `O_NOCTTY` on the
file; then the file is judged by its descriptor, never its name again: a regular file with one
name (a hard link, or a file removed since, is not), no larger than the caller's cap, read to at
most the cap. The caller decodes the bytes and decides what a final link means.

It depends on the standard library alone and knows nothing of cordis or bh-02. Its gate is in
`pyproject.toml`; the functions that read the filesystem are named in its purity budget,
since reading links is what they are for, and so is the opener.
