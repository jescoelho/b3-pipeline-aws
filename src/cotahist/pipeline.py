"""Pipeline local: COTAHIST bruto -> Parquet particionado (ano/mes), espelhando o que o Glue fará na AWS.

PARA LEIGOS — o que este arquivo faz?
    É a "linha de montagem" que roda no SEU computador, sem nuvem:

        arquivo .TXT da B3  ->  parser (lê e converte)  ->  pastas com arquivos Parquet

    Parquet é um formato de arquivo feito para análise: guarda os dados por
    coluna (não por linha), ocupa muito menos espaço que o texto original e
    permite ler só as colunas necessárias.

    Os arquivos são separados em pastas por ano e mês:
        data/curated/cotahist/ano=2020/mes=3/...parquet
    Isso se chama PARTICIONAMENTO. Quem consulta "março de 2020" abre só uma
    pasta e ignora as outras — mais rápido e mais barato.

    Este script é a versão "de bancada" para aprender e testar. A versão
    para volumes grandes, na nuvem, é glue/cotahist_to_parquet.py.

Como rodar (a partir da raiz do projeto):
    PYTHONPATH=src python -m cotahist.pipeline --raw data/raw/COTAHIST_A2020.TXT --out data/curated/cotahist
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .parser import read_cotahist


def run(raw_files: list[Path], out_dir: Path) -> dict:
    """Converte uma lista de arquivos brutos em Parquet particionado.

    Args:
        raw_files: caminhos dos arquivos COTAHIST (.TXT) de entrada.
        out_dir: pasta de saída onde as subpastas ano=.../mes=... serão criadas.

    Returns:
        Um pequeno resumo: quantas linhas foram processadas e quantos segundos levou.
    """
    t0 = time.time()  # cronômetro, para registrar o tempo gasto
    rows = 0
    for f in raw_files:
        df = read_cotahist(f)  # etapa 1: ler e converter o texto em tabela
        if df.empty:
            continue
        rows += len(df)
        table = pa.Table.from_pandas(df, preserve_index=False)  # etapa 2: formato de tabela do Arrow/Parquet
        pq.write_to_dataset(  # etapa 3: gravar, separando em pastas ano=/mes=
            table,
            root_path=str(out_dir),
            partition_cols=["ano", "mes"],
            compression="snappy",  # compressão rápida, boa para análise
            # Se reexecutar, substitui só as partições já existentes (não duplica dados).
            existing_data_behavior="delete_matching",
        )
    return {"linhas": rows, "segundos": round(time.time() - t0, 2)}


if __name__ == "__main__":
    # Bloco executado só quando o arquivo é chamado pela linha de comando
    # (e não quando importado por outro módulo, como nos testes).
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", nargs="+", required=True)  # um ou mais arquivos de entrada
    ap.add_argument("--out", default="data/curated/cotahist")  # pasta de saída
    a = ap.parse_args()
    print(run([Path(p) for p in a.raw], Path(a.out)))
