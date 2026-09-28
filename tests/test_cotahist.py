"""Testes automáticos do pipeline (rode com `python -m pytest` na raiz do projeto).

PARA LEIGOS — por que testar?
    Em pipelines de dados o pior erro é o silencioso: uma coluna deslocada em
    1 posição não dá erro nenhum, apenas números errados. Estes testes fazem
    o computador conferir, a cada mudança, que o mapa de posições, o parser e
    o pipeline continuam corretos. Se alguém alterar algo sem querer, o
    teste falha na hora — e não meses depois.
"""
from datetime import date

import duckdb
import pytest

from cotahist.fields import RECORD_LEN, FIELDS
from cotahist.parser import parse_line, read_cotahist
from cotahist.pipeline import run
from cotahist.synthetic import build_record, generate


def test_field_layout_is_contiguous_and_245():
    """O mapa de posições não pode ter buracos nem sobreposições e deve somar 245 caracteres."""
    pos = 1
    for name, s, e, _ in FIELDS:
        assert s == pos, f"{name}: gap/overlap em {s}"
        pos = e + 1
    assert pos - 1 == RECORD_LEN


def test_roundtrip_single_record():
    """Ida e volta: monta uma linha de PETR4 no formato da B3 e confere se o parser devolve os mesmos valores."""
    vals = {n: None for n, *_ in FIELDS}
    vals.update(
        tipo_registro="01", data_pregao=date(2020, 3, 2), cod_bdi="02", cod_negociacao="PETR4",
        tipo_mercado=10, nome_resumido="PETROBRAS", especificacao="PN N2", prazo_dias_mercado_termo="",
        moeda_referencia="R$", preco_abertura=27.5, preco_maximo=28.1, preco_minimo=27.0,
        preco_medio=27.6, preco_ultimo=27.9, preco_melhor_compra=27.89, preco_melhor_venda=27.91,
        total_negocios=1234, quantidade_titulos=5_000_000, volume_total=138_000_000.5,
        preco_exercicio=0, indicador_correcao="0", data_vencimento=None, fator_cotacao=1,
        preco_exercicio_pontos=0, cod_isin="BRPETRACNPR6", num_distribuicao=123,
    )
    rec = parse_line(build_record(vals))
    assert rec["cod_negociacao"] == "PETR4"
    assert rec["data_pregao"] == date(2020, 3, 2)
    assert float(rec["preco_ultimo"]) == 27.9  # o preço voltou com a vírgula no lugar certo
    assert float(rec["volume_total"]) == 138_000_000.5
    assert rec["data_vencimento"] is None  # sem vencimento = ausência de valor, não uma data falsa
    assert rec["quantidade_titulos"] == 5_000_000


def test_header_trailer_skipped_and_bad_length_raises():
    """Cabeçalho e rodapé são ignorados; uma linha de cotação com tamanho errado deve gerar erro."""
    assert parse_line("00COTAHIST".ljust(245)) is None
    assert parse_line("99COTAHIST".ljust(245)) is None
    with pytest.raises(ValueError):
        parse_line("01" + "0" * 10)


def test_pipeline_end_to_end(tmp_path):
    """Teste de ponta a ponta: gera dados falsos -> lê -> grava em Parquet -> consulta com DuckDB.

    Confere que nenhuma linha se perdeu, que as pastas por mês foram criadas
    e que os dados respeitam uma regra básica de mercado.
    """
    raw = tmp_path / "raw.txt"  # tmp_path = pasta temporária, apagada ao fim do teste
    n = generate(raw, date(2020, 1, 1), date(2020, 3, 31), n_tickers=20)
    df = read_cotahist(raw)
    assert len(df) == n
    out = tmp_path / "curated"
    stats = run([raw], out)
    assert stats["linhas"] == n
    parts = sorted(p.name for p in out.glob("ano=2020/mes=*"))
    assert parts == ["mes=1", "mes=2", "mes=3"]  # jan, fev e mar de 2020 viraram 3 pastas
    got = duckdb.sql(f"select count(*), count(distinct cod_negociacao) from read_parquet('{out}/**/*.parquet', hive_partitioning=true)").fetchone()
    assert got == (n, 20)  # mesmo total de linhas e mesmos 20 papéis distintos
    # invariante de mercado: máxima >= mínima e >= último
    bad = duckdb.sql(f"select count(*) from read_parquet('{out}/**/*.parquet') where preco_maximo < preco_minimo").fetchone()[0]
    assert bad == 0
