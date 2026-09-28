-- PARA LEIGOS — o que é este arquivo?
--   Athena é o serviço da AWS que permite consultar arquivos guardados no S3 usando SQL
--   (a linguagem padrão de consulta a dados), sem manter um banco de dados ligado.
--   Você paga apenas pela quantidade de dado que cada consulta precisa ler.
--   Este arquivo tem 4 consultas para rodar, em ordem, no console do Athena:
--     1) cria a "tabela" (na verdade, um mapa que aponta para os arquivos Parquet);
--     2) e 3) mostram a economia do particionamento (mesma pergunta, com e sem filtro de mês);
--     4) calcula a volatilidade de cada papel — a validação com dados reais.

-- 1) Tabela externa com PARTITION PROJECTION (sem MSCK REPAIR / crawler).
--    Troque <BUCKET> e <DATABASE> pelos outputs do terraform.
--    "EXTERNAL" = a tabela não guarda dado nenhum: só descreve onde os arquivos estão
--    e quais colunas têm. Apagar a tabela NÃO apaga os arquivos do S3.
--    "PARTITION PROJECTION" = o Athena deduz sozinho quais pastas existem (ano=1986..2030,
--    mes=1..12) em vez de listá-las no S3 a cada consulta; é mais rápido e dispensa manutenção.
CREATE EXTERNAL TABLE IF NOT EXISTS <DATABASE>.cotahist (
  data_pregao date,
  cod_bdi string,
  cod_negociacao string,
  tipo_mercado int,
  nome_resumido string,
  especificacao string,
  moeda_referencia string,
  preco_abertura decimal(18,2),
  preco_maximo decimal(18,2),
  preco_minimo decimal(18,2),
  preco_medio decimal(18,2),
  preco_ultimo decimal(18,2),
  preco_melhor_compra decimal(18,2),
  preco_melhor_venda decimal(18,2),
  total_negocios int,
  quantidade_titulos bigint,
  volume_total decimal(18,2),
  preco_exercicio decimal(18,2),
  data_vencimento date,
  fator_cotacao int,
  cod_isin string
)
PARTITIONED BY (ano int, mes int)
STORED AS PARQUET
LOCATION 's3://<BUCKET>/curated/cotahist/'
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.ano.type' = 'integer',
  'projection.ano.range' = '1986,2030',
  'projection.mes.type' = 'integer',
  'projection.mes.range' = '1,12',
  'storage.location.template' = 's3://<BUCKET>/curated/cotahist/ano=${ano}/mes=${mes}/'
);

-- 2) Consulta com poda de partição: escaneia só 1 mês.
--    Pergunta: "em março de 2020, quais papéis (mercado à vista) tiveram maior volume financeiro
--    e qual foi o preço médio de fechamento de cada um?" (top 20)
--    O filtro `ano = 2020 AND mes = 3` faz o Athena abrir só a pasta ano=2020/mes=3.
SELECT cod_negociacao, avg(preco_ultimo) AS media, sum(volume_total) AS volume
FROM <DATABASE>.cotahist
WHERE ano = 2020 AND mes = 3 AND tipo_mercado = 10
GROUP BY 1 ORDER BY volume DESC LIMIT 20;

-- 3) Mesma consulta SEM filtro de partição: compare "Data scanned" na aba de execução.
--    Sem dizer o mês, o Athena precisa ler todas as pastas. Na rodada real, isso foi ~11,5x mais
--    dado lido (5,35 MB contra 477 KB) — a diferença entre as duas é o que o particionamento economiza.
SELECT cod_negociacao, avg(preco_ultimo) AS media, sum(volume_total) AS volume
FROM <DATABASE>.cotahist
WHERE tipo_mercado = 10
GROUP BY 1 ORDER BY volume DESC LIMIT 20;

-- 4) Retorno diário e volatilidade 21d por papel (window functions).
--    "Retorno" = quanto o preço variou de um dia para o outro (em escala logarítmica, padrão em finanças).
--    "Volatilidade" = o quanto esses retornos oscilam numa janela de 21 pregões (~1 mês),
--    multiplicada por raiz de 252 (dias úteis do ano) para virar uma taxa anual.
--    Volatilidade alta = preço "nervoso". Em PETR4, sobe de ~12% (jan/2020) para ~200% (mar/2020,
--    crash da pandemia): um evento real, o que confirma que o pipeline lê os dados corretamente.
--    "lag(...)" busca o preço do dia anterior do MESMO papel; "OVER (... ROWS BETWEEN 20 PRECEDING ...)"
--    define a janela móvel (o dia atual + os 20 anteriores).
WITH r AS (
  SELECT cod_negociacao, data_pregao,
         ln(preco_ultimo / lag(preco_ultimo) OVER (PARTITION BY cod_negociacao ORDER BY data_pregao)) AS ret
  FROM <DATABASE>.cotahist
  WHERE ano = 2020 AND tipo_mercado = 10
)
SELECT cod_negociacao, data_pregao,
       stddev(ret) OVER (PARTITION BY cod_negociacao ORDER BY data_pregao ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) * sqrt(252) AS vol_anualizada
FROM r
ORDER BY data_pregao DESC LIMIT 50;
