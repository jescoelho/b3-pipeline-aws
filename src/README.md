# src/ — o código Python que roda no seu computador

Esta pasta contém o pacote `cotahist`, que lê o arquivo de cotações da B3 e o transforma em dados organizados, **sem precisar de AWS**. É a "bancada de trabalho" do projeto: serve para aprender, testar e conferir a lógica antes de rodá-la na nuvem (a versão em escala está em [`../glue/`](../glue/cotahist_to_parquet.py)).

## O problema que este código resolve

A B3 publica um arquivo de texto em que cada linha tem **exatamente 245 caracteres**, sem vírgulas nem colunas. O significado de cada trecho depende da posição: os caracteres 13 a 24 são o código da ação (`PETR4`), e `0000000002790` nas posições 57 a 69 significa R$ 27,90 (o ponto decimal é omitido). Este código:

1. descreve essas posições (`fields.py`);
2. corta e converte cada linha (`parser.py`);
3. grava o resultado em Parquet, separado por ano e mês (`pipeline.py`);
4. fabrica arquivos de teste no mesmo formato (`synthetic.py`).

## Estrutura

```
src/
└── cotahist/
    ├── __init__.py    Marca a pasta como pacote Python e resume os módulos
    ├── fields.py      O mapa de posições: "caracteres 13 a 24 = código do papel"
    ├── parser.py      Transforma o texto da B3 em uma tabela
    ├── pipeline.py    Grava a tabela em Parquet, em pastas ano=/mes=
    └── synthetic.py   Gera arquivos falsos no formato da B3, para teste e treino
```

## Como os módulos se encaixam

```
fields.py  ──(usado por)──►  parser.py  ──►  pipeline.py  ──►  data/curated/cotahist/ano=2020/mes=3/…parquet
    │                                            ▲
    └──────(usado por)──►  synthetic.py ──► arquivo .TXT falso ──┘  (entra no lugar do arquivo real)
```

`fields.py` é a base: tanto o parser (que lê) quanto o gerador (que escreve) consultam o mesmo mapa. Por isso, se o layout da B3 mudar, este é o ponto principal de ajuste.

## O que cada módulo oferece

| Módulo | Função | O que faz |
|---|---|---|
| `fields.py` | `FIELDS`, `RECORD_LEN` | Lista dos 26 campos (nome, posição inicial, posição final, tipo) e o tamanho da linha (245) |
| `parser.py` | `_conv(raw, kind)` | Converte um pedaço de texto para o tipo certo (número, decimal, data) |
| | `parse_line(line)` | Converte uma linha inteira; ignora cabeçalho e rodapé e recusa linha de tamanho errado |
| | `iter_records(lines)` | Percorre muitas linhas e entrega só as cotações válidas |
| | `read_cotahist(path)` | Lê o arquivo todo e devolve uma tabela com as colunas `ano` e `mes` |
| `pipeline.py` | `run(raw_files, out_dir)` | Converte arquivos brutos em Parquet particionado e devolve linhas processadas e tempo gasto |
| `synthetic.py` | `build_record(values)` | Monta uma linha de 245 caracteres a partir de um dicionário |
| | `generate(path, start, end, n_tickers, seed)` | Cria um arquivo completo com papéis e preços inventados |

## Como usar

Rode sempre a partir da **raiz do projeto** (uma pasta acima de `src/`). O `PYTHONPATH=src` diz ao Python onde encontrar o pacote `cotahist`.

```bash
pip install pandas pyarrow duckdb pytest

# 1) Gerar um arquivo falso (500 papéis, 2010 a 2020)
PYTHONPATH=src python -m cotahist.synthetic --start 2010-01-01 --end 2020-12-31 --tickers 500 --out data/raw/SINT.TXT

# 2) Converter para Parquet particionado (serve para o arquivo falso ou para o real da B3)
PYTHONPATH=src python -m cotahist.pipeline --raw data/raw/SINT.TXT --out data/curated/cotahist
```

Para dados reais, baixe o arquivo com [`../scripts/download_cotahist.sh`](../scripts/download_cotahist.sh) e aponte `--raw` para `data/raw/COTAHIST_A2020.TXT`.

Também é possível usar as funções em outro script Python:

```python
from cotahist.parser import read_cotahist

df = read_cotahist("data/raw/COTAHIST_A2020.TXT")
print(df[df.cod_negociacao == "PETR4"][["data_pregao", "preco_ultimo"]].head())
```

## Pontos de atenção

- **Layout duplicado:** o mesmo mapa de posições existe também em [`../glue/cotahist_to_parquet.py`](../glue/cotahist_to_parquet.py). Se você alterar `fields.py`, altere o script do Glue também.
- **Dados sintéticos não são mercado:** os preços do `synthetic.py` são sorteados ao acaso. Use-os para testar o pipeline, nunca para análise financeira.
- **Codificação `latin-1`:** o arquivo da B3 usa essa codificação para entender acentos. Ler com outra codificação corrompe nomes de empresas.
- **Linha de tamanho errado gera erro de propósito:** é melhor parar do que gravar dados trocados de coluna em silêncio.
- **Confira o layout oficial:** o mapa foi escrito a partir do layout da B3 e validado com o arquivo de 2020. Para outros anos, confira o PDF de layout que acompanha o download.

## Como verificar que tudo funciona

Os testes ficam em [`../tests/`](../tests/test_cotahist.py). Na raiz do projeto:

```bash
python -m pytest
```

Eles conferem o mapa de posições, a conversão de uma linha da PETR4 e o pipeline completo, de ponta a ponta.

## Para saber mais

- [`../docs/GUIA_DO_PROJETO.md`](../docs/GUIA_DO_PROJETO.md): o projeto inteiro, passo a passo, para leigos.
- [`../docs/ESTUDO.md`](../docs/ESTUDO.md): os conceitos (largura fixa, Parquet, particionamento).
