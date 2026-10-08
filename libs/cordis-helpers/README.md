# cordis-helpers

Conveniences a cordis plugin may reach for. cordis itself stays the paper's mechanisms and
nothing else; this package is patterns built on them, with no domain in them.

- **`Registry[T]`**: entries by name, each registration returning its own remover. The
  paper's service broker (section 6.2) minus any notion of what the entries are: one row
  binds a registry, many rows `acquire(registry.register, name, entry)` into it, consumers
  depend on the registry and never on a contributor. Registrations are commutative
  (Definition 44): every subset can be withdrawn in any order.
- **`Hooks[F]`**: a set of callables with the same discipline, for guards, listeners and
  policies where order must not matter.
- **`perform(jobs, failed)`** (and `Job`): work a row owns, put on a queue by code that runs
  in another row's task (a slash command, which runs in the task of the row that read the line)
  and run one job at a time by the row's own `background(perform(jobs, failed))`. A job that
  restarts what the caller depends on would cancel itself half-way in the caller's task; in the
  row's own, it runs to the end, and leaves with the row. A job that fails is reported to
  `failed` (one line; awaited when it returns an awaitable, as a row telling the person does)
  and the next still runs.
- **`config_home(environ, home)`** and **`walked(path)`** (and `MOST_LINKS`): paths as every
  package that trusts a file by where it is must see them alike. `config_home` is where the
  person's configuration lives (`$XDG_CONFIG_HOME`, else `home`'s `.config`); `walked` is every
  place reading an absolute path goes through, from the top (each directory and link on the
  way, a link where it sits and then where it leads, a `..` from where the links before it led,
  at most `MOST_LINKS` links), then where it ends: whoever may write any of them chooses what is
  read. Not built on cordis at all; here because the packages of a family may import nothing of
  each other's, and two copies of a check like this one drift.

Depends on `cordis` only. A plugin that uses it depends on `cordis-helpers`, which is a
library, not another plugin.
