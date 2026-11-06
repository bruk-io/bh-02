"""The seal's decisions: which seeds a key gives, and which set a sealed run takes."""

import pytest

from scenarios.seal import Entry, SealError, commitment, decide_run, key_from, open_seeds, sealed_seeds, spent

KEY = bytes(range(32))
OTHER = bytes(range(1, 33))


def test_a_key_gives_the_same_sealed_seeds_every_time():
    assert sealed_seeds(KEY, "code", 0, 5) == sealed_seeds(KEY, "code", 0, 5)


def test_another_key_gives_other_seeds_so_the_repository_alone_cannot_build_the_set():
    assert set(sealed_seeds(KEY, "code", 0, 50)).isdisjoint(sealed_seeds(OTHER, "code", 0, 50))


def test_families_and_sets_get_seeds_of_their_own_and_none_is_an_open_seed():
    sets = [set(sealed_seeds(KEY, family, n, 50)) for family in ("code", "incident") for n in (0, 1)]
    seen: set[int] = set()
    for s in sets:
        assert s.isdisjoint(seen)
        seen |= s
    assert seen.isdisjoint(open_seeds(1000))


def test_the_repository_holds_a_digest_that_names_the_key_without_giving_it():
    assert commitment(KEY) == commitment(KEY) != commitment(OTHER)
    assert KEY.hex() not in commitment(KEY)


def test_a_run_takes_the_lowest_set_no_run_has_used():
    entries = [
        Entry("d", "built", "code", 0),
        Entry("d", "run", "code", 0, "v1"),
        Entry("d", "run", "code", 2, "v2"),
        Entry("d", "run", "incident", 1, "v1"),
    ]
    assert spent(entries, "code") == {0, 2}
    assert decide_run(entries, "code", dirty=()) == 1
    assert decide_run(entries, "incident", dirty=()) == 0


def test_building_a_set_does_not_spend_it():
    assert decide_run([Entry("d", "built", "code", 0)], "code", dirty=()) == 0


def test_a_run_is_refused_while_the_envelope_code_has_uncommitted_changes():
    with pytest.raises(SealError, match="commit them first"):
        decide_run([], "code", dirty=("compressors/envelope_log.py",))


def test_a_key_is_thirty_two_bytes_of_hex():
    assert key_from(KEY.hex() + "\n") == KEY
    for bad in ("", "zz" * 32, KEY.hex()[:-2]):
        with pytest.raises(SealError, match="32 bytes"):
            key_from(bad)
