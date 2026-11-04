"""Lines that differ only in numbers are one template, unless a number is the anomaly (R5)."""

import random

from compressors.cli import fold_text


def _access_log(n: int, odd: dict[int, str]) -> str:
    rng = random.Random(1)
    lines = []
    for i in range(n):
        status = odd.get(i, "200")
        when = f"03/Nov/2026:10:{i // 60 % 60:02d}:{i % 60:02d}"
        lines.append(f'10.0.0.{rng.randint(1, 250)} - - [{when}] "GET /a" {status} {rng.randint(200, 9000)}')
    return "\n".join(lines)


def test_one_500_among_2000_200s_stands_out():
    out = fold_text(_access_log(2000, {1234: "500"}), budget=500, quiet=True).text
    assert "is 500 in 1 line like:" in out
    assert "1235: 10.0.0." in out and '" 500 ' in out  # the line itself, at its number


def test_a_non_zero_failure_count_among_zeros_stands_out():
    lines = [f"2026-11-03T10:00:{i % 60:02d}Z suite {i}: 120 passed, 0 failed" for i in range(400)]
    lines[300] = "2026-11-03T10:05:00Z suite 300: 117 passed, 3 failed"
    out = fold_text("\n".join(lines), budget=300, quiet=True).text
    assert "3 failed" in out


def test_numbers_that_always_vary_do_not_split_a_run():
    lines = [
        f"2026-11-03T10:{i // 60 % 60:02d}:{i % 60:02d}Z heartbeat seq={i} took {100 + i % 7}ms"
        for i in range(1000)
    ]
    out = fold_text("\n".join(lines), budget=300, quiet=True).text
    assert "  1000  <*>:<*>:<*> heartbeat seq=<*> took <*>" in out and "anomalies: none" in out
