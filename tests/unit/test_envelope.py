import pytest

from compressors.common import estimate_tokens
from compressors.envelope import (
    NOTHING,
    Count,
    Level,
    Part,
    Recipe,
    Role,
    build,
    compose,
    fit,
    nothing,
    priority,
    render,
)


def _part(role: Role, sizes: tuple[int, ...]) -> Part:
    """A part whose levels are one line of `n` words each, fullest first."""
    return Part(role, tuple(Level(f"{n} words", (" ".join(["word"] * n),)) for n in sizes))


def _parts() -> tuple[Part, ...]:
    return (
        _part(Role.SHAPE, (200, 50)),
        _part(Role.ANOMALIES, (200, 20)),
        _part(Role.SAMPLES, (300, 10)),
        nothing(Role.NAV),
    )


def test_every_part_starts_terse_and_the_budget_raises_them_in_priority_order():
    parts = _parts()
    terse = fit(parts, 1)
    assert terse.chosen == (1, 1, 1, 0)  # nothing fits: the tersest levels are what is shown
    roomy = fit(parts, 10_000)
    assert roomy.chosen == (0, 0, 0, 0)
    some = fit(parts, estimate_tokens(render(parts, (0, 1, 1, 0))) + 5)  # room for one full part
    assert some.chosen == (0, 1, 1, 0)  # the shape claims it first
    first_samples = fit(
        parts, estimate_tokens(render(parts, (1, 1, 0, 0))) + 5, priority("samples,shape,anomalies,nav")
    )
    assert first_samples.chosen == (1, 1, 0, 0)


def test_a_part_that_shows_nothing_is_left_out_and_the_rest_are_titled_and_indented():
    parts = (
        Part(Role.SHAPE, (Level("", ("a: array[3] of object",)),)),
        Part(Role.ANOMALIES, (Level("none", ()),)),
        Part(Role.SAMPLES, (NOTHING,)),
        Part(Role.NAV, (Level("", ("jq '.a[0]' FILE",)),)),
    )
    assert (
        render(parts, (0, 0, 0, 0))
        == "shape:\n  a: array[3] of object\nanomalies: none\nget more:\n  jq '.a[0]' FILE"
    )


def test_producers_run_in_order_each_given_the_parts_before_it():
    seen = []

    def shape(data: str, /) -> Part:
        return Part(Role.SHAPE, (Level("", (data,), (Count(".a", 3),)),))

    def spot(_data: str, shape: Part, /) -> Part:
        seen.append(shape.levels[0].claims)
        return nothing(Role.ANOMALIES)

    def sample(_data: str, _shape: Part, anomalies: Part, /) -> Part:
        seen.append(anomalies.role)
        return nothing(Role.SAMPLES)

    def nav(_data: str, _shape: Part, _anomalies: Part, samples: Part, /) -> Part:
        seen.append(samples.role)
        return nothing(Role.NAV)

    env = compose(Recipe(shape, spot, sample, nav), "the data", 100)
    assert seen == [(Count(".a", 3),), Role.ANOMALIES, Role.SAMPLES]
    assert env.text() == "shape:\n  the data" and env.claims() == (Count(".a", 3),)
    with pytest.raises(ValueError, match="the samples producer made a nav part"):
        build(Recipe(shape, spot, lambda _d, _s, _a, /: nothing(Role.NAV), nav), "x")


def test_a_priority_names_each_part_once():
    assert priority("nav, samples,shape,anomalies")[0] is Role.NAV
    with pytest.raises(ValueError, match="names each part once"):
        priority("shape,anomalies,samples")
    with pytest.raises(ValueError, match="at least one level"):
        Part(Role.SHAPE, ())
