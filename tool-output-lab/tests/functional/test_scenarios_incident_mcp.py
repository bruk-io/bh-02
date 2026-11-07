"""The incident family's MCP server, through FastMCP's in-memory client, and layer 1 on its outputs."""

import asyncio

from fastmcp import Client

from compressors.config import FoldConfig
from evals.l1 import check
from evals.tasks import BUDGET
from scenarios import incident
from scenarios.incident_mcp import server
from scenarios.l1 import incident_probe_tasks


def test_the_server_offers_the_tools_and_answers_from_its_world():
    w = incident.world(3)

    async def ask() -> tuple[list[str], str]:
        async with Client(server(w)) as c:
            names = [t.name for t in await c.list_tools()]
            result = await c.call_tool("get_logs", {"service": w.fault.victim, "since": "14:00"})
            return names, result.content[0].text  # type: ignore[union-attr]

    names, text = asyncio.run(ask())
    assert sorted(names) == sorted(incident.TOOLS)
    assert text == incident.get_logs(w, w.fault.victim, since="14:00")


def test_every_probe_of_a_world_folds_to_an_envelope_that_states_nothing_false():
    for size in ("M", "L"):
        rows = [
            check(t, BUDGET, True, "schema", FoldConfig())
            for t in incident_probe_tasks(incident.world(2, size))
        ]
        assert rows and [r.violations for r in rows if r.violations] == []
