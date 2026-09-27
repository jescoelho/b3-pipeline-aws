#!/usr/bin/env bash
# Baixa COTAHIST anual da B3 (ex.: ./scripts/download_cotahist.sh 2020 2021 2022).
# Rode na SUA máquina (o site da B3 pode bloquear ambientes de nuvem).
# Confira a URL atual no site da B3 (Market Data e Índices > Serviços de dados > Mercado a Vista > Histórico de cotações),
# pois o endereço já mudou no passado.
set -euo pipefail
mkdir -p data/raw
for ano in "$@"; do
  url="https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A${ano}.ZIP"
  echo "-> $url"
  curl -fL -o "data/raw/COTAHIST_A${ano}.ZIP" "$url"
  unzip -o "data/raw/COTAHIST_A${ano}.ZIP" -d data/raw
done
