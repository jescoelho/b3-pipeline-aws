"""Job AWS Glue (PySpark): COTAHIST bruto (S3, latin-1, posição fixa) -> Parquet particionado por ano/mes.

PARA LEIGOS — o que é este arquivo?
    É a versão "em escala" do que src/cotahist/parser.py + pipeline.py fazem no
    seu computador. A lógica é a mesma (cortar cada linha de 245 caracteres nas
    posições certas, converter os tipos, gravar em Parquet por ano/mês), mas
    aqui ela roda no AWS Glue usando Spark.

    Spark divide o arquivo em pedaços e processa vários pedaços ao mesmo tempo,
    em várias máquinas. Para 235 mil linhas isso é exagero; para bilhões de
    linhas é a única forma viável. Para escalar, aumenta-se o número de máquinas
    ("workers") no Terraform — a lógica não muda.

    O Glue lê e grava no S3 (o "HD na nuvem" da AWS). Este script é enviado ao
    S3 e registrado como job pelo Terraform (terraform/main.tf).

Argumentos (--nome valor):
  --raw_path      s3://bucket/raw/cotahist/       (onde estão os .TXT originais)
  --curated_path  s3://bucket/curated/cotahist/   (onde gravar o Parquet pronto)
Layout idêntico a src/cotahist/fields.py (mantenha os dois em sincronia).
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# ---- Preparação: o "cerimonial" obrigatório de todo job Glue ----
# Recebe os parâmetros (--raw_path, --curated_path) passados pelo Glue e liga o motor Spark.
args = getResolvedOptions(sys.argv, ["JOB_NAME", "raw_path", "curated_path"])
sc = SparkContext()
glue = GlueContext(sc)
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

# ---- Etapa 1: ler o texto bruto ----
# Lê como linhas de texto; latin-1 evita quebrar acentos de nomes de empresas.
# Cada linha vira uma linha da tabela, numa única coluna chamada "l".
lines = (
    spark.read.option("encoding", "ISO-8859-1").text(args["raw_path"]).withColumnRenamed("value", "l")
)
# Descarta cabeçalho ("00") e rodapé ("99"): só as linhas de cotação ("01") interessam.
lines = lines.filter(F.substring("l", 1, 2) == "01")


# ---- Funções auxiliares: cada uma corta um trecho da linha e converte o tipo ----
def s(a, b):  # substring 1-based inclusivo
    """Texto: pega os caracteres de a até b e remove espaços das pontas."""
    return F.trim(F.substring("l", a, b - a + 1))


def p(a, b, scale):
    """Número com casas decimais implícitas: pega a..b e divide por `scale` (100 = 2 casas).

    Ex.: "0000000002790" / 100 = 27.90
    """
    return (F.substring("l", a, b - a + 1).cast("decimal(20,0)") / scale).cast("decimal(18,2)")


def d(a, b):
    """Data AAAAMMDD -> data de verdade. Os valores 00000000 e 99991231 significam "sem data"."""
    v = F.substring("l", a, b - a + 1)
    return F.when(v.isin("00000000", "99991231"), F.lit(None)).otherwise(F.to_date(v, "yyyyMMdd"))


# ---- Etapa 2: cortar as posições e dar nome a cada coluna ----
# Cada linha abaixo equivale a uma linha do mapa em fields.py (ex.: d(3, 10) = "data do pregão, posições 3 a 10").
# Campos que não são usados nas análises (ex.: prazo a termo, indicador de correção) ficam de fora.
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
# Cria as colunas ano e mes, que definirão as pastas de saída.
df = df.withColumn("ano", F.year("data_pregao")).withColumn("mes", F.month("data_pregao"))

# ---- Etapa 3: gravar em Parquet, separado por ano/mês ----
# Evita o "small files problem": reparticiona pelas colunas de partição antes de escrever.
# (Sem isso, cada máquina gravaria um pedacinho de cada mês: centenas de arquivos minúsculos,
#  que deixam as consultas lentas. Com isso, cada mês vira poucos arquivos de bom tamanho.)
(
    df.repartition("ano", "mes")
    .write.mode("overwrite")  # com partitionOverwriteMode=dynamic só reescreve partições tocadas
    .option("partitionOverwriteMode", "dynamic")
    .partitionBy("ano", "mes")
    .parquet(args["curated_path"])
)
# Avisa o Glue que o job terminou com sucesso.
job.commit()
