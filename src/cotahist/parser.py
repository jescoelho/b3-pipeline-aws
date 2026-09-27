"""Parser do COTAHIST (posição fixa, latin-1) -> DataFrame tipado."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

from .fields import FIELDS, RECORD_LEN

ENCODING = "latin-1"


def _conv(raw: str, kind: str):
    raw = raw.strip()
    if kind == "s":
        return raw or None
    if raw == "":
        return None
    if kind == "i":
        return int(raw)
    if kind == "p2":
        return Decimal(int(raw)) / 100
    if kind == "p6":
        return Decimal(int(raw)) / 1_000_000
    if kind == "d":
        # B3 usa 99991231 como "sem vencimento"
        if raw in ("00000000", "99991231"):
            return None
        return datetime.strptime(raw, "%Y%m%d").date()
    raise ValueError(kind)


def parse_line(line: str) -> dict | None:
    """Retorna dict para registros tipo '01' (cotação); None para header/trailer."""
    if line[:2] != "01":
        return None
    if len(line.rstrip("\r\n")) != RECORD_LEN:
        raise ValueError(f"registro com tamanho {len(line.rstrip(chr(13) + chr(10)))} != {RECORD_LEN}")
    return {n: _conv(line[s - 1 : e], k) for n, s, e, k in FIELDS}


def iter_records(lines: Iterable[str]) -> Iterator[dict]:
    for line in lines:
        rec = parse_line(line)
        if rec is not None:
            yield rec


def read_cotahist(path: str | Path) -> pd.DataFrame:
    with open(path, encoding=ENCODING) as fh:
        df = pd.DataFrame(iter_records(fh))
    if df.empty:
        return df
    for col in df.columns:
        if col.startswith(("preco_", "volume_")):
            df[col] = df[col].astype(float)
    df["data_pregao"] = pd.to_datetime(df["data_pregao"])
    df["ano"] = df["data_pregao"].dt.year.astype("int32")
    df["mes"] = df["data_pregao"].dt.month.astype("int32")
    return df
