"""Gera um arquivo COTAHIST sintético (mesmo layout de 245 bytes) para testes e treino local."""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

from .fields import FIELDS, RECORD_LEN


def _fmt(kind: str, width: int, value) -> str:
    if kind == "s":
        return str(value)[:width].ljust(width)
    if kind == "i":
        return str(int(value)).zfill(width)
    if kind == "p2":
        return str(int(round(value * 100))).zfill(width)
    if kind == "p6":
        return str(int(round(value * 1_000_000))).zfill(width)
    if kind == "d":
        return value.strftime("%Y%m%d") if value else "99991231"
    raise ValueError(kind)


def build_record(values: dict) -> str:
    out = []
    for name, s, e, kind in FIELDS:
        out.append(_fmt(kind, e - s + 1, values[name]))
    line = "".join(out)
    assert len(line) == RECORD_LEN, len(line)
    return line


def _business_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def generate(path: Path, start: date, end: date, n_tickers: int, seed: int = 42) -> int:
    rnd = random.Random(seed)
    tickers = [f"{''.join(rnd.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))}{rnd.choice([3, 4, 11])}" for _ in range(n_tickers)]
    prices = {t: rnd.uniform(5, 80) for t in tickers}
    n = 0
    with open(path, "w", encoding="latin-1", newline="") as fh:
        header = "00COTAHIST.SINTETICO".ljust(RECORD_LEN)
        fh.write(header + "\r\n")
        for d in _business_days(start, end):
            for t in tickers:
                p0 = prices[t]
                p1 = max(0.5, p0 * (1 + rnd.gauss(0, 0.02)))
                hi, lo = max(p0, p1) * 1.01, min(p0, p1) * 0.99
                qty = rnd.randint(1_000, 5_000_000)
                rec = {
                    "tipo_registro": "01",
                    "data_pregao": d,
                    "cod_bdi": "02",
                    "cod_negociacao": t,
                    "tipo_mercado": 10,
                    "nome_resumido": f"EMPRESA {t[:4]}",
                    "especificacao": "ON NM",
                    "prazo_dias_mercado_termo": "",
                    "moeda_referencia": "R$",
                    "preco_abertura": p0,
                    "preco_maximo": hi,
                    "preco_minimo": lo,
                    "preco_medio": (p0 + p1) / 2,
                    "preco_ultimo": p1,
                    "preco_melhor_compra": p1 * 0.999,
                    "preco_melhor_venda": p1 * 1.001,
                    "total_negocios": rnd.randint(10, 90_000),
                    "quantidade_titulos": qty,
                    "volume_total": qty * (p0 + p1) / 2,
                    "preco_exercicio": 0,
                    "indicador_correcao": "0",
                    "data_vencimento": None,
                    "fator_cotacao": 1,
                    "preco_exercicio_pontos": 0,
                    "cod_isin": f"BR{t[:4]}ACNOR0",
                    "num_distribuicao": 100,
                }
                fh.write(build_record(rec) + "\r\n")
                prices[t] = p1
                n += 1
        fh.write(("99COTAHIST.SINTETICO".ljust(RECORD_LEN)) + "\r\n")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw/COTAHIST_SINT.TXT")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2020-12-31")
    ap.add_argument("--tickers", type=int, default=300)
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = generate(out, date.fromisoformat(a.start), date.fromisoformat(a.end), a.tickers)
    print(f"{total} registros -> {out}")
