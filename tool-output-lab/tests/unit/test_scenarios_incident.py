"""The incident family's worlds: each truth agrees with what the tools return."""

import json
import re

import pytest

from evals.truth import Exact
from scenarios.incident import (
    Task,
    failures,
    get_logs,
    get_metrics,
    list_deploys,
    list_pods,
    minute_name,
    world,
)
from scenarios.l2 import tools_for


def test_a_seed_builds_the_same_world_and_another_seed_another():
    assert world(2) == world(2)
    assert world(2).lines != world(3).lines


def test_the_count_is_the_number_of_5xx_lines_the_victims_logs_show():
    w = world(1)
    shown = get_logs(w, w.fault.victim, since="14:00")
    assert failures(w, 60, 120) == len(re.findall(r" status=5\d\d ", shown)) > 0


def test_the_failures_start_at_the_rollout_and_name_the_rolled_out_service():
    w = world(4)
    errors = [line for line in get_logs(w, w.fault.victim).splitlines() if " status=504 " in line]
    assert errors and all(f"upstream {w.fault.service} timed out" in line for line in errors)
    assert min(line[11:16] for line in errors) >= minute_name(w.fault.minute)


def test_one_deploy_has_the_rollouts_version_and_it_is_the_faulty_services():
    w = world(5)
    deploys = json.loads(list_deploys(w))["deploys"]
    assert [d["service"] for d in deploys if d["version"] == w.fault.new] == [w.fault.service]


def test_the_stale_pods_are_the_rolled_out_services_pods_on_another_version():
    w = world(6)
    pods = json.loads(list_pods(w))["items"]
    stale = {
        p["name"]
        for p in pods
        if p["labels"]["app"] == w.fault.service and p["labels"]["version"] != w.fault.new
    }
    assert 1 <= len(stale) <= 2
    assert all(p["labels"]["version"] == w.fault.old for p in pods if p["name"] in stale)


def test_the_gap_is_the_one_minute_its_service_logged_nothing():
    w = world(7)
    service, gap = w.gap
    minutes = {line[11:16] for line in get_logs(w, service).splitlines()}
    assert minute_name(gap) not in minutes
    assert all(minute_name(m) in minutes for m in range(120) if m != gap)


def test_the_noisy_service_has_noise_and_no_5xx():
    w = world(8)
    logs = get_logs(w, w.noisy)
    assert "cache miss" in logs and "status=499" in logs
    assert all(point["value"] == 0 for point in json.loads(get_metrics(w, w.noisy, "errors"))["points"])


def test_a_call_for_a_service_that_does_not_exist_names_where_to_look():
    with pytest.raises(ValueError, match="list_services names them"):
        get_logs(world(0), "nonsense")


def test_an_incident_session_gets_the_incident_tools_and_the_shell():
    t = Task("incident-M-0-cause", "spot", "Which deploy?", Exact("1"), ())
    tools = tools_for(t).split(",")
    assert "mcp__incident__get_logs" in tools and "Bash" in tools and "Edit" not in tools
