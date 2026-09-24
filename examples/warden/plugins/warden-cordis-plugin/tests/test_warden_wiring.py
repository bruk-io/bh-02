"""The rows driven by hand: the effects they yield, performed by nobody."""

from cordis.testing import drive
from warden_cordis_plugin import ProcessConfig, Processes, registry, supervised


async def test_the_registry_row_binds_one_processes_value_and_runs_nothing() -> None:
    effects = await drive(registry())
    assert [e.name for e in effects] == ["bind"]
    assert effects[0].args[0] == "processes"


async def test_a_supervised_row_enters_the_process_then_registers_it_under_its_name() -> None:
    config = ProcessConfig(name="web", command=("true",))
    effects = await drive(supervised(config=config, processes=Processes()))
    assert [e.name for e in effects] == ["enter", "acquire"]
    assert effects[1].args[1] == "web"
