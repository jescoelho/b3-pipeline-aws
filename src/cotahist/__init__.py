"""Pacote `cotahist`: tudo que é necessário para ler e converter o arquivo COTAHIST da B3.

Guia rápido dos módulos (detalhes em cada arquivo e em docs/GUIA_DO_PROJETO.md):
    fields.py     mapa das posições: "caracteres 13 a 24 = código do papel"
    parser.py     lê o texto da B3 e o transforma em tabela
    pipeline.py   grava a tabela em Parquet, separada por ano/mês
    synthetic.py  fabrica arquivos falsos no formato da B3, para teste e treino
"""
