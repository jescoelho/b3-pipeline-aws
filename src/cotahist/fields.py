"""Layout do arquivo COTAHIST da B3 (registro de 245 bytes, posição fixa).

Posições são 1-based e inclusivas, conforme o layout oficial da B3
("Séries Históricas de Cotações"). CONFIRA contra o PDF de layout que
acompanha o download antes de usar em algo que importe.

kind:
  s    -> string (strip)
  i    -> inteiro
  p2   -> decimal com 2 casas implícitas (ex.: 0000000012345 -> 123.45)
  p6   -> decimal com 6 casas implícitas
  d    -> data AAAAMMDD
"""

RECORD_LEN = 245

# (nome, inicio, fim, kind)
FIELDS = [
    ("tipo_registro", 1, 2, "s"),
    ("data_pregao", 3, 10, "d"),
    ("cod_bdi", 11, 12, "s"),
    ("cod_negociacao", 13, 24, "s"),
    ("tipo_mercado", 25, 27, "i"),
    ("nome_resumido", 28, 39, "s"),
    ("especificacao", 40, 49, "s"),
    ("prazo_dias_mercado_termo", 50, 52, "s"),
    ("moeda_referencia", 53, 56, "s"),
    ("preco_abertura", 57, 69, "p2"),
    ("preco_maximo", 70, 82, "p2"),
    ("preco_minimo", 83, 95, "p2"),
    ("preco_medio", 96, 108, "p2"),
    ("preco_ultimo", 109, 121, "p2"),
    ("preco_melhor_compra", 122, 134, "p2"),
    ("preco_melhor_venda", 135, 147, "p2"),
    ("total_negocios", 148, 152, "i"),
    ("quantidade_titulos", 153, 170, "i"),
    ("volume_total", 171, 188, "p2"),
    ("preco_exercicio", 189, 201, "p2"),
    ("indicador_correcao", 202, 202, "s"),
    ("data_vencimento", 203, 210, "d"),
    ("fator_cotacao", 211, 217, "i"),
    ("preco_exercicio_pontos", 218, 230, "p6"),
    ("cod_isin", 231, 242, "s"),
    ("num_distribuicao", 243, 245, "i"),
]

# colspecs 0-based, semi-abertos, para pandas.read_fwf
COLSPECS = [(s - 1, e) for _, s, e, _ in FIELDS]
NAMES = [n for n, *_ in FIELDS]
