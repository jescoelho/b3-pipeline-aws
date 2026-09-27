-- 1) Tabela externa com PARTITION PROJECTION (sem MSCK REPAIR / crawler).
--    Troque <BUCKET> e <DATABASE> pelos outputs do terraform.
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
SELECT cod_negociacao, avg(preco_ultimo) AS media, sum(volume_total) AS volume
FROM <DATABASE>.cotahist
WHERE ano = 2020 AND mes = 3 AND tipo_mercado = 10
GROUP BY 1 ORDER BY volume DESC LIMIT 20;

-- 3) Mesma consulta SEM filtro de partição: compare "Data scanned" na aba de execução.
SELECT cod_negociacao, avg(preco_ultimo) AS media, sum(volume_total) AS volume
FROM <DATABASE>.cotahist
WHERE tipo_mercado = 10
GROUP BY 1 ORDER BY volume DESC LIMIT 20;

-- 4) Retorno diário e volatilidade 21d por papel (window functions).
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
