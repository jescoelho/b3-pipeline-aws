"""Job AWS Glue (PySpark): COTAHIST bruto (S3, latin-1, posição fixa) -> Parquet particionado por ano/mes.

Argumentos (--nome valor):
  --raw_path      s3://bucket/raw/cotahist/
  --curated_path  s3://bucket/curated/cotahist/
Layout idêntico a src/cotahist/fields.py (mantenha os dois em sincronia).
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(sys.argv, ["JOB_NAME", "raw_path", "curated_path"])
sc = SparkContext()
glue = GlueContext(sc)
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

# Lê como linhas de texto; latin-1 evita quebrar acentos de nomes de empresas.
lines = (
    spark.read.option("encoding", "ISO-8859-1").text(args["raw_path"]).withColumnRenamed("value", "l")
)
lines = lines.filter(F.substring("l", 1, 2) == "01")


def s(a, b):  # substring 1-based inclusivo
    return F.trim(F.substring("l", a, b - a + 1))


def p(a, b, scale):
    return (F.substring("l", a, b - a + 1).cast("decimal(20,0)") / scale).cast("decimal(18,2)")


def d(a, b):
    v = F.substring("l", a, b - a + 1)
    return F.when(v.isin("00000000", "99991231"), F.lit(None)).otherwise(F.to_date(v, "yyyyMMdd"))


df = lines.select(
    d(3, 10).alias("data_pregao"),
    s(11, 12).alias("cod_bdi"),
    s(13, 24).alias("cod_negociacao"),
    F.substring("l", 25, 3).cast("int").alias("tipo_mercado"),
    s(28, 39).alias("nome_resumido"),
    s(40, 49).alias("especificacao"),
    s(53, 56).alias("moeda_referencia"),
    p(57, 69, 100).alias("preco_abertura"),
    p(70, 82, 100).alias("preco_maximo"),
    p(83, 95, 100).alias("preco_minimo"),
    p(96, 108, 100).alias("preco_medio"),
    p(109, 121, 100).alias("preco_ultimo"),
    p(122, 134, 100).alias("preco_melhor_compra"),
    p(135, 147, 100).alias("preco_melhor_venda"),
    F.substring("l", 148, 5).cast("int").alias("total_negocios"),
    F.substring("l", 153, 18).cast("long").alias("quantidade_titulos"),
    p(171, 188, 100).alias("volume_total"),
    p(189, 201, 100).alias("preco_exercicio"),
    d(203, 210).alias("data_vencimento"),
    F.substring("l", 211, 7).cast("int").alias("fator_cotacao"),
    s(231, 242).alias("cod_isin"),
)
df = df.withColumn("ano", F.year("data_pregao")).withColumn("mes", F.month("data_pregao"))

# Evita o "small files problem": reparticiona pelas colunas de partição antes de escrever.
(
    df.repartition("ano", "mes")
    .write.mode("overwrite")  # com partitionOverwriteMode=dynamic só reescreve partições tocadas
    .option("partitionOverwriteMode", "dynamic")
    .partitionBy("ano", "mes")
    .parquet(args["curated_path"])
)
job.commit()
