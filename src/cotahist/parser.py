"""Parser do COTAHIST (posição fixa, latin-1) -> DataFrame tipado.

PARA LEIGOS — o que é um "parser"?
    "Parsear" é interpretar um texto e transformá-lo em dados organizados.
    O arquivo da B3 é uma sequência de linhas de 245 caracteres; o parser
    "corta" cada linha nas posições descritas em fields.py, converte cada
    pedaço para o tipo certo (número, data, texto) e devolve uma tabela
    (DataFrame do pandas, parecido com uma planilha) que o computador
    consegue somar, filtrar e consultar.

    Fluxo, de dentro para fora:
        _conv()        converte UM pedaço de texto (ex.: "0000000002790" -> 27.90)
        parse_line()   converte UMA linha inteira em um dicionário {campo: valor}
        iter_records() percorre várias linhas, ignorando cabeçalho/rodapé
        read_cotahist() lê o arquivo todo e devolve a tabela final, com colunas ano e mes
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

from .fields import FIELDS, RECORD_LEN

# Codificação de caracteres do arquivo da B3. "latin-1" é o padrão antigo que
# entende acentos do português (ç, ã, é). Ler com a codificação errada
# transformaria "AÇÃO" em símbolos estranhos.
ENCODING = "latin-1"


def _conv(raw: str, kind: str):
    """Converte um pedaço de texto para o tipo indicado em fields.py (s, i, p2, p6 ou d).

    Campos vazios viram None (ausência de valor), nunca zero — "não informado"
    é diferente de "zero".
    """
    raw = raw.strip()  # tira espaços das pontas
    if kind == "s":
        return raw or None  # texto vazio vira "sem valor"
    if raw == "":
        return None
    if kind == "i":
        return int(raw)
    if kind == "p2":
        # Números monetários vêm sem ponto decimal. Dividir por 100 devolve os centavos.
        # Usa Decimal (e não float) para evitar erros de arredondamento em dinheiro.
        return Decimal(int(raw)) / 100
    if kind == "p6":
        return Decimal(int(raw)) / 1_000_000
    if kind == "d":
        # B3 usa 99991231 como "sem vencimento" (e 00000000 como data em branco)
        if raw in ("00000000", "99991231"):
            return None
        return datetime.strptime(raw, "%Y%m%d").date()
    raise ValueError(kind)


def parse_line(line: str) -> dict | None:
    """Retorna dict para registros tipo '01' (cotação); None para header/trailer.

    O arquivo tem 3 tipos de linha: cabeçalho ("00", 1ª linha), cotações ("01",
    milhões de linhas) e rodapé ("99", última linha). Só as cotações interessam.

    Se uma linha de cotação não tiver exatamente 245 caracteres, o arquivo está
    corrompido ou o layout mudou: melhor parar com erro do que gravar dado
    trocado de coluna em silêncio.
    """
    if line[:2] != "01":
        return None
    if len(line.rstrip("\r\n")) != RECORD_LEN:
        raise ValueError(f"registro com tamanho {len(line.rstrip(chr(13) + chr(10)))} != {RECORD_LEN}")
    # Para cada campo do mapa: corta a faixa [início, fim] da linha e converte.
    # (s - 1 porque o layout conta posições a partir de 1, e o Python a partir de 0.)
    return {n: _conv(line[s - 1 : e], k) for n, s, e, k in FIELDS}


def iter_records(lines: Iterable[str]) -> Iterator[dict]:
    """Percorre linhas de texto e entrega (uma a uma) só os registros de cotação já convertidos."""
    for line in lines:
        rec = parse_line(line)
        if rec is not None:
            yield rec


def read_cotahist(path: str | Path) -> pd.DataFrame:
    """Lê um arquivo COTAHIST inteiro e devolve uma tabela (DataFrame) pronta para análise.

    Além das colunas do arquivo, cria `ano` e `mes` — usadas depois para
    separar os dados em pastas (particionamento, ver pipeline.py).
    """
    with open(path, encoding=ENCODING) as fh:
        df = pd.DataFrame(iter_records(fh))
    if df.empty:
        return df
    # Preços e volumes passam de Decimal para float, formato que o Parquet e as
    # ferramentas de análise tratam de forma nativa e rápida.
    for col in df.columns:
        if col.startswith(("preco_", "volume_")):
            df[col] = df[col].astype(float)
    df["data_pregao"] = pd.to_datetime(df["data_pregao"])
    df["ano"] = df["data_pregao"].dt.year.astype("int32")
    df["mes"] = df["data_pregao"].dt.month.astype("int32")
    return df
