"""Layer 2's job list: building it reads the task registry, which reads real files on this host."""

from evals.l2 import select


def test_jobs_pair_every_task_with_its_channels_conditions():
    jobs = select(["json"], ["spot"], ["M"], None)
    assert {c for _, c in jobs} == {"native", "fold", "fold-inline", "fold-all"}
    jobs = select(["python"], ["locate"], ["L"], None)
    assert {c for _, c in jobs} == {"native", "fold-tool"} and all(t.path for t, _ in jobs)
