"""The incident family's tools as an MCP server over stdio, for headless Claude Code runs.

    SCENARIO_SEED=3 SCENARIO_SIZE=M python -m scenarios.incident_mcp

The world comes from the environment, so the model never sees which seed it is. Each tool returns
what `scenarios.incident` gives for the call: everything it has, as many real MCP servers do.
"""

import os

from fastmcp import FastMCP

from scenarios import incident


def server(w: incident.World) -> FastMCP:
    """An MCP server whose tools answer from `w`."""
    mcp = FastMCP("incident")

    @mcp.tool
    def list_services() -> str:
        """The services in production (namespace prod): each one's team, the services it calls, and
        its replica count."""
        return incident.list_services(w)

    @mcp.tool
    def list_pods(namespace: str = "prod") -> str:
        """Every pod in a namespace: its labels (app, team, version), node, IP, phase, readiness,
        restarts, start time and image."""
        return incident.list_pods(w, namespace)

    @mcp.tool
    def list_deploys() -> str:
        """Every deploy of the last few days: the service, the version, when, who, and a note."""
        return incident.list_deploys(w)

    @mcp.tool
    def get_logs(service: str, since: str = "13:00", until: str = "15:00") -> str:
        """Every log line a service wrote on 2026-11-03 from `since` up to `until` (HH:MM or HH:MM:SS,
        UTC). The logs kept cover 13:00 to 15:00."""
        return incident.get_logs(w, service, since, until)

    @mcp.tool
    def get_metrics(service: str, metric: str = "errors", since: str = "13:00", until: str = "15:00") -> str:
        """A per-minute series for a service on 2026-11-03: requests, errors (responses with status
        500 or more) or p95_ms, from `since` up to `until` (HH:MM, UTC)."""
        return incident.get_metrics(w, service, metric, since, until)

    return mcp


def main() -> None:
    w = incident.world(int(os.environ["SCENARIO_SEED"]), os.environ.get("SCENARIO_SIZE", "M"))
    server(w).run(show_banner=False)


if __name__ == "__main__":
    main()
