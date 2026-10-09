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

It depends on the standard library alone and knows nothing of cordis or bh-02. Its gate is in
`pyproject.toml`; the three functions that read the filesystem are named in its purity budget,
since reading links is what they are for.
