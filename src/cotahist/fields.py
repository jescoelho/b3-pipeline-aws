"""Layout do arquivo COTAHIST da B3 (registro de 245 bytes, posição fixa).

PARA LEIGOS — o que é este arquivo?
    O arquivo da B3 é um texto sem separadores (sem vírgula, sem tabulação).
    Cada linha tem exatamente 245 caracteres, e o "significado" de cada trecho
    depende da POSIÇÃO. Exemplo: os caracteres 13 a 24 são sempre o código do
    papel (PETR4, VALE3...). Este arquivo é o "mapa" que diz qual faixa de
    posições corresponde a qual informação. É como uma planilha desenhada
    com régua: coluna A vai da posição 1 à 2, coluna B da 3 à 10, e assim por diante.

    Todo o resto do projeto (parser, gerador de dados falsos, testes) consulta
    este mapa. Se o layout da B3 mudar, este é o único lugar do lado Python
    que precisa ser ajustado (e o script do Glue, que tem uma cópia — ver
    glue/cotahist_to_parquet.py).

Detalhes técnicos:
    Posições são 1-based e inclusivas, conforme o layout oficial da B3
    ("Séries Históricas de Cotações"). CONFIRA contra o PDF de layout que
    acompanha o download antes de usar em algo que importe.

    kind (o "tipo" de cada campo):
      s    -> string (texto; espaços nas pontas são removidos)
      i    -> inteiro
      p2   -> decimal com 2 casas implícitas (ex.: 0000000012345 -> 123.45)
              "implícitas" = o ponto decimal não aparece no arquivo; é preciso
              dividir por 100. Assim, 0000000002790 significa R$ 27,90.
      p6   -> decimal com 6 casas implícitas (divide por 1.000.000)
      d    -> data no formato AAAAMMDD (ex.: 20200302 = 2 de março de 2020)
"""

# Tamanho de cada linha de cotação, em caracteres. Linhas de outro tamanho são consideradas corrompidas.
RECORD_LEN = 245

# Uma linha por campo: (nome_da_coluna, posição_inicial, posição_final, tipo).
# Ex.: ("cod_negociacao", 13, 24, "s") = "os caracteres 13 a 24 são o código do papel, em texto".
FIELDS = [
    ("tipo_registro", 1, 2, "s"),  # "01" = cotação; "00" = cabeçalho do arquivo; "99" = rodapé
    ("data_pregao", 3, 10, "d"),  # dia do pregão (dia de negociação na bolsa)
    ("cod_bdi", 11, 12, "s"),  # código BDI: categoria do papel (ex.: lote padrão, fracionário)
    ("cod_negociacao", 13, 24, "s"),  # o "ticker": PETR4, VALE3...
    ("tipo_mercado", 25, 27, "i"),  # 10 = mercado à vista; outros números = opções, termo etc.
    ("nome_resumido", 28, 39, "s"),  # nome curto da empresa
    ("especificacao", 40, 49, "s"),  # tipo da ação (ON = ordinária, PN = preferencial...)
    ("prazo_dias_mercado_termo", 50, 52, "s"),  # só para operações a termo
    ("moeda_referencia", 53, 56, "s"),  # "R$" para reais
    ("preco_abertura", 57, 69, "p2"),  # preço do primeiro negócio do dia
    ("preco_maximo", 70, 82, "p2"),  # maior preço do dia
    ("preco_minimo", 83, 95, "p2"),  # menor preço do dia
    ("preco_medio", 96, 108, "p2"),  # preço médio do dia
    ("preco_ultimo", 109, 121, "p2"),  # preço do último negócio (o "fechamento")
    ("preco_melhor_compra", 122, 134, "p2"),  # melhor oferta de compra ao fim do dia
    ("preco_melhor_venda", 135, 147, "p2"),  # melhor oferta de venda ao fim do dia
    ("total_negocios", 148, 152, "i"),  # quantos negócios (transações) ocorreram
    ("quantidade_titulos", 153, 170, "i"),  # quantas ações/títulos foram negociados
    ("volume_total", 171, 188, "p2"),  # valor financeiro total negociado, em R$
    ("preco_exercicio", 189, 201, "p2"),  # só para opções: preço de exercício
    ("indicador_correcao", 202, 202, "s"),  # só para opções: indicador de correção
    ("data_vencimento", 203, 210, "d"),  # só para opções/termo: data de vencimento
    ("fator_cotacao", 211, 217, "i"),  # 1 = cotado por unidade; 1000 = cotado por lote de mil
    ("preco_exercicio_pontos", 218, 230, "p6"),  # opções referenciadas em pontos
    ("cod_isin", 231, 242, "s"),  # código internacional do papel (identificador único mundial)
    ("num_distribuicao", 243, 245, "i"),  # nº de distribuição do papel
]

# Versões derivadas do mapa acima, prontas para bibliotecas que pedem "faixas" em vez de posições.
# colspecs 0-based, semi-abertos, para pandas.read_fwf (posição 1 do layout vira índice 0 em Python)
COLSPECS = [(s - 1, e) for _, s, e, _ in FIELDS]
# Só a lista de nomes de coluna, na ordem do arquivo.
NAMES = [n for n, *_ in FIELDS]
