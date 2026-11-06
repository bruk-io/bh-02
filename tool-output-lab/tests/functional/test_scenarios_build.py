"""The code-and-tests family built for real: git, the tests through uv, and layer 1 on the outputs
(it runs git and pytest on this host, so these are functional tests)."""

import subprocess

from compressors.config import FoldConfig
from evals.l1 import check
from evals.tasks import BUDGET
from scenarios import code
from scenarios.l1 import probe_tasks


def test_a_world_builds_to_the_same_commits_and_its_tests_fail_only_from_the_regression(tmp_path):
    w = code.world(0)
    built = code.build(w, tmp_path / "a")  # build refuses a world whose test report disagrees with it
    assert code.build(w, tmp_path / "b").shas == built.shas
    before = built.shas[w.regression.at - 1]
    subprocess.run(["git", "checkout", "-q", before], cwd=built.root, check=True)
    passed = subprocess.run(
        ["./run-tests", "-q"], cwd=built.root, capture_output=True, text=True, check=False
    )
    assert passed.returncode == 0, passed.stdout[-500:]


def test_every_probe_of_a_world_folds_to_an_envelope_that_states_nothing_false(tmp_path):
    w = code.world(1)
    built = code.build(w, tmp_path / "w")
    rows = [
        check(t, BUDGET, query_on=True, view="schema", config=FoldConfig()) for t in probe_tasks(w, built)
    ]
    assert rows and [r.violations for r in rows if r.violations] == []
    assert any(r.branch == "code-python" for r in rows)  # a whole-file view folds as code
