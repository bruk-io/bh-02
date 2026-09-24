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

Depends on `cordis` only. A plugin that uses it depends on `cordis-helpers`, which is a
library, not another plugin.
