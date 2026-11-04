"""Fetch a real corpus into corpus/real/ (untracked: the data keeps its own licence).

    ./lab fetch hdfs

hdfs: Loghub's HDFS_v1 from Hugging Face (logfit-project/HDFS_v1: a Hadoop cluster's log over two
days, 11.2M lines, each block labelled anomalous or not by the people who ran it; free for research
use), reduced to corpus/real/hdfs/blocks.jsonl: every block whose first line falls in the log's
first 100,000 lines, with its whole lifecycle from all 11.2M (a block is written in seconds and
replicated or deleted hours later, and its label may rest on those later lines). The five Parquet
shards are read one at a time and deleted after. Each line is rendered as HDFS.log writes it
(`081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block ...`):

    {"block": "blk_-1608999687919862906", "anomaly": 0, "lines": [[1, "081109 203518 ..."], ...]}

The eval tasks (`evals.tasks`) are built from that file. Runs on Python 3.13 with pyarrow, which
has no build for 3.15 yet; the rest of the lab never imports this module.
"""

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

_LAB = Path(__file__).resolve().parent.parent
_HDFS = _LAB / "corpus" / "real" / "hdfs"
_SHARDS = "https://huggingface.co/api/datasets/logfit-project/HDFS_v1/parquet/default/train/{}.parquet"
_N_SHARDS = 5
_FIRST_LINES = 100_000  # blocks that start here, with every line they have in the whole log


def _download(url: str, to: Path) -> None:
    if to.is_file():
        return
    to.parent.mkdir(parents=True, exist_ok=True)
    part = to.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=600) as r, part.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    part.rename(to)


def _rendered(row: dict[str, Any]) -> str:
    return f"{row['date']} {row['time']} {row['pid']} {row['level']} {row['component']}: {row['content']}"


def hdfs() -> int:
    import pyarrow as pa  # only this command needs it
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    blocks: dict[str, dict[str, Any]] = {}
    lines: dict[str, list[list[Any]]] = defaultdict(list)
    for k in range(_N_SHARDS):
        shard = _HDFS / f"HDFS_v1-{k}.parquet"
        _download(_SHARDS.format(k), shard)
        table = pq.read_table(shard)
        if k == 0:  # the blocks: those that start in the first lines
            head = table.filter(pc.less_equal(table["line_number"], _FIRST_LINES)).to_pylist()
            for row in head:
                blocks.setdefault(row["block_id"], {"block": row["block_id"], "anomaly": int(row["anomaly"])})
        mine = table.filter(pc.is_in(table["block_id"], value_set=pa.array(list(blocks)))).to_pylist()
        for row in mine:
            lines[row["block_id"]].append([row["line_number"], _rendered(row)])
        shard.unlink()  # the shards are 87 MB each: keep only what the tasks read
        print(f"shard {k}: {len(mine)} lines of {len(blocks)} blocks", flush=True)
    out = _HDFS / "blocks.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for b, record in blocks.items():
            f.write(json.dumps(record | {"lines": sorted(lines[b])}) + "\n")
    anomalous = sum(r["anomaly"] for r in blocks.values())
    print(f"{out}: {len(blocks)} blocks, {anomalous} anomalous, {sum(len(v) for v in lines.values())} lines")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", choices=("hdfs",))
    ns = parser.parse_args(argv)
    return {"hdfs": hdfs}[ns.source]()


if __name__ == "__main__":
    sys.exit(main())
