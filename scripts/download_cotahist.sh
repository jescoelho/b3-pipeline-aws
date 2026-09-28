#!/usr/bin/env bash
# PARA LEIGOS: este script baixa da B3 o arquivo histórico de cotações de um ou mais anos
# (cada ano é um arquivo .ZIP com todos os negócios daquele ano), descompacta e deixa o
# .TXT na pasta data/raw/, que é o ponto de partida do pipeline.
#
# Baixa COTAHIST anual da B3 (ex.: ./scripts/download_cotahist.sh 2020 2021 2022).
# Rode na SUA máquina (o site da B3 pode bloquear ambientes de nuvem).
# Confira a URL atual no site da B3 (Market Data e Índices > Serviços de dados > Mercado a Vista > Histórico de cotações),
# pois o endereço já mudou no passado.
set -euo pipefail          # para no primeiro erro, em vez de seguir adiante com arquivo faltando
mkdir -p data/raw          # cria a pasta de destino, se ainda não existir
for ano in "$@"; do        # repete para cada ano informado na linha de comando
  url="https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A${ano}.ZIP"
  echo "-> $url"
  curl -fL -o "data/raw/COTAHIST_A${ano}.ZIP" "$url"   # baixa (-f: falha se o site devolver erro)
  unzip -o "data/raw/COTAHIST_A${ano}.ZIP" -d data/raw  # descompacta, sobrescrevendo se já existir
done
