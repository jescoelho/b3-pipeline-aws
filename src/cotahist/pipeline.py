"""Pipeline local: COTAHIST bruto -> Parquet particionado (ano/mes), espelhando o que o Glue fará na AWS."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .parser import read_cotahist


def run(raw_files: list[Path], out_dir: Path) -> dict:
    t0 = time.time()
    rows = 0
    for f in raw_files:
        df = read_cotahist(f)
        if df.empty:
            continue
        rows += len(df)
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_to_dataset(
            table,
            root_path=str(out_dir),
            partition_cols=["ano", "mes"],
            compression="snappy",
            existing_data_behavior="delete_matching",
        )
    return {"linhas": rows, "segundos": round(time.time() - t0, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", nargs="+", required=True)
    ap.add_argument("--out", default="data/curated/cotahist")
    a = ap.parse_args()
    print(run([Path(p) for p in a.raw], Path(a.out)))
