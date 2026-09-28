"""Gera um arquivo COTAHIST sintético (mesmo layout de 245 bytes) para testes e treino local.

PARA LEIGOS — por que fabricar dados falsos?
    Para testar o pipeline sem depender do download da B3 e sem correr riscos.
    Este módulo cria um arquivo com o MESMO formato do arquivo real (linhas de
    245 caracteres), mas com empresas e preços inventados. Serve para:
      - os testes automáticos (tests/test_cotahist.py), que precisam de um arquivo previsível;
      - treinar o pipeline em grande volume (ex.: 500 papéis x 10 anos) sem baixar nada.

    É o caminho inverso do parser: o parser transforma texto em dados;
    este módulo transforma dados em texto no formato da B3.

    Os preços seguem um "passeio aleatório" (cada dia o preço varia ~2% para cima
    ou para baixo, ao acaso). É realista o bastante para testar, mas NÃO representa
    o mercado de verdade — nunca use estes dados para análise financeira.

Como rodar:
    PYTHONPATH=src python -m cotahist.synthetic --start 2010-01-01 --end 2020-12-31 --tickers 500 --out data/raw/SINT.TXT
"""
from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

from .fields import FIELDS, RECORD_LEN


def _fmt(kind: str, width: int, value) -> str:
    """Formata UM valor no jeito que o arquivo da B3 espera (inverso de parser._conv).

    Ex.: o preço 27.90 com largura 13 vira "0000000002790" (sem ponto, zeros à esquerda).
    Texto é completado com espaços à direita; números, com zeros à esquerda.
    """
    if kind == "s":
        return str(value)[:width].ljust(width)  # corta se passar do tamanho, completa com espaços
    if kind == "i":
        return str(int(value)).zfill(width)  # zfill = completa com zeros à esquerda
    if kind == "p2":
        return str(int(round(value * 100))).zfill(width)  # remove o ponto: 27.90 -> 2790
    if kind == "p6":
        return str(int(round(value * 1_000_000))).zfill(width)
    if kind == "d":
        return value.strftime("%Y%m%d") if value else "99991231"  # sem data = "sem vencimento"
    raise ValueError(kind)


def build_record(values: dict) -> str:
    """Monta UMA linha de 245 caracteres a partir de um dicionário {campo: valor}."""
    out = []
    for name, s, e, kind in FIELDS:
        out.append(_fmt(kind, e - s + 1, values[name]))  # largura do campo = fim - início + 1
    line = "".join(out)
    # Autoverificação: se algum campo saiu com tamanho errado, o layout está inconsistente.
    assert len(line) == RECORD_LEN, len(line)
    return line


def _business_days(start: date, end: date):
    """Entrega cada dia útil (segunda a sexta) entre duas datas. Não considera feriados."""
    d = start
    while d <= end:
        if d.weekday() < 5:  # 0 = segunda ... 4 = sexta; 5 e 6 = fim de semana
            yield d
        d += timedelta(days=1)


def generate(path: Path, start: date, end: date, n_tickers: int, seed: int = 42) -> int:
    """Cria o arquivo sintético completo e devolve quantos registros de cotação foram escritos.

    Args:
        path: onde gravar o arquivo.
        start, end: período coberto (só dias úteis).
        n_tickers: quantos "papéis" inventados.
        seed: semente do sorteio. Com a mesma semente o arquivo sai sempre igual,
              o que torna os testes reproduzíveis.
    """
    rnd = random.Random(seed)
    # Inventa códigos de papel no estilo brasileiro: 4 letras + 3, 4 ou 11 (ex.: "ABCD4").
    tickers = [f"{''.join(rnd.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))}{rnd.choice([3, 4, 11])}" for _ in range(n_tickers)]
    # Preço inicial de cada papel: sorteado entre R$ 5 e R$ 80.
    prices = {t: rnd.uniform(5, 80) for t in tickers}
    n = 0
    with open(path, "w", encoding="latin-1", newline="") as fh:
        # Todo arquivo da B3 começa com uma linha de cabeçalho ("00") ...
        header = "00COTAHIST.SINTETICO".ljust(RECORD_LEN)
        fh.write(header + "\r\n")
        for d in _business_days(start, end):
            for t in tickers:
                p0 = prices[t]  # preço de abertura = fechamento do dia anterior
                # Preço de fechamento: varia ~2% (distribuição normal), mínimo de R$ 0,50.
                p1 = max(0.5, p0 * (1 + rnd.gauss(0, 0.02)))
                # Máxima e mínima do dia: 1% além do maior/menor entre abertura e fechamento.
                # Isso garante a regra de mercado "máxima >= mínima" (verificada nos testes).
                hi, lo = max(p0, p1) * 1.01, min(p0, p1) * 0.99
                qty = rnd.randint(1_000, 5_000_000)
                rec = {
                    "tipo_registro": "01",
                    "data_pregao": d,
                    "cod_bdi": "02",
                    "cod_negociacao": t,
                    "tipo_mercado": 10,  # 10 = mercado à vista
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
                    "volume_total": qty * (p0 + p1) / 2,  # quantidade x preço médio
                    "preco_exercicio": 0,
                    "indicador_correcao": "0",
                    "data_vencimento": None,
                    "fator_cotacao": 1,
                    "preco_exercicio_pontos": 0,
                    "cod_isin": f"BR{t[:4]}ACNOR0",
                    "num_distribuicao": 100,
                }
                fh.write(build_record(rec) + "\r\n")
                prices[t] = p1  # o fechamento de hoje vira a abertura de amanhã
                n += 1
        # ... e termina com uma linha de rodapé ("99").
        fh.write(("99COTAHIST.SINTETICO".ljust(RECORD_LEN)) + "\r\n")
    return n


if __name__ == "__main__":
    # Bloco executado só pela linha de comando: lê as opções e gera o arquivo.
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw/COTAHIST_SINT.TXT")  # arquivo de saída
    ap.add_argument("--start", default="2020-01-01")  # primeiro dia
    ap.add_argument("--end", default="2020-12-31")  # último dia
    ap.add_argument("--tickers", type=int, default=300)  # nº de papéis inventados
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)  # cria a pasta se não existir
    total = generate(out, date.fromisoformat(a.start), date.fromisoformat(a.end), a.tickers)
    print(f"{total} registros -> {out}")
