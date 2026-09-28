# PARA LEIGOS — o que é este arquivo?
#   Terraform é uma ferramenta de "infraestrutura como código": em vez de clicar no console
#   da AWS criando recursos manualmente, descrevemos tudo neste arquivo e o Terraform cria
#   (`terraform apply`) ou destrói (`terraform destroy`) tudo de uma vez, de forma repetível.
#
#   Este arquivo cria, em ordem:
#     1. Um "bucket" S3          -> o HD na nuvem onde ficam os dados brutos, os prontos e os resultados
#     2. O script do Glue        -> enviado ao bucket
#     3. Uma "role" IAM          -> a permissão que o robô (Glue) usa para acessar o bucket
#     4. O job do Glue           -> o trabalhador que converte texto da B3 em Parquet
#     5. Banco + workgroup Athena-> onde as consultas SQL são organizadas e limitadas
#     6. Um alerta de orçamento  -> e-mail se o gasto se aproximar do limite

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Diz ao Terraform em qual região da AWS criar tudo (data center virtual; us-east-1 = Virgínia, EUA).
provider "aws" {
  region = var.region
}

# ---------- Parâmetros de entrada (você informa ao rodar `terraform apply -var ...`) ----------
variable "region" {
  type    = string
  default = "us-east-1"
}

variable "prefix" {
  description = "Prefixo único para os buckets (ex.: seunome-b3lab)"
  type        = string
}

variable "budget_email" {
  description = "E-mail que recebe o alerta de custo"
  type        = string
}

variable "budget_usd" {
  type    = number
  default = 10 # teto mensal de gasto, em dólares
}

# Descobre o número da conta AWS de quem está rodando (usado para tornar o nome do bucket único).
data "aws_caller_identity" "me" {}

locals {
  # Nomes de bucket S3 são únicos no mundo inteiro; prefixo + número da conta evita colisões.
  bucket = "${var.prefix}-${data.aws_caller_identity.me.account_id}"
}

# ---------- S3 ----------
# O bucket é organizado em "pastas": raw/ (texto original), curated/ (Parquet pronto),
# scripts/ (código do Glue) e athena-results/ (resultados das consultas).
resource "aws_s3_bucket" "lake" {
  bucket        = local.bucket
  force_destroy = true # é laboratório: destroy apaga tudo
}

# Segurança: bloqueia qualquer forma de tornar o bucket público na internet.
resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Segurança: todo arquivo é gravado criptografado (AES-256) automaticamente.
resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Envia o script do Glue (glue/cotahist_to_parquet.py) para o bucket, de onde o Glue o executa.
# O `etag` refaz o envio automaticamente quando o script muda.
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.lake.id
  key    = "scripts/cotahist_to_parquet.py"
  source = "${path.module}/../glue/cotahist_to_parquet.py"
  etag   = filemd5("${path.module}/../glue/cotahist_to_parquet.py")
}

# ---------- IAM do Glue ----------
# IAM = controle de acesso da AWS. Por padrão NINGUÉM (nem robôs) tem permissão para nada.
# Aqui damos ao Glue exatamente o que ele precisa, e mais nada.

# Regra 1: "o serviço Glue pode assumir esta identidade (role)".
data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

# A identidade (role) do robô Glue.
resource "aws_iam_role" "glue" {
  name               = "${var.prefix}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

# Permissões básicas de funcionamento do Glue (política pronta mantida pela AWS).
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Regra 2: "pode ler, gravar, apagar e listar arquivos NESTE bucket" (e só neste).
data "aws_iam_policy_document" "glue_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
  }
}

resource "aws_iam_role_policy" "glue_s3" {
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_s3.json
}

# ---------- Glue job (limite de workers = teto de custo) ----------
# O job é a "tarefa cadastrada": qual script rodar, com quantas máquinas e com quais parâmetros.
# Ele NÃO roda sozinho: é disparado manualmente (`aws glue start-job-run`).
resource "aws_glue_job" "cotahist" {
  name              = "${var.prefix}-cotahist-to-parquet"
  role_arn          = aws_iam_role.glue.arn  # a identidade/permissões definidas acima
  glue_version      = "4.0"
  worker_type       = "G.1X"  # tamanho de cada máquina (pequeno)
  number_of_workers = 2       # quantas máquinas em paralelo; poucas = custo baixo
  timeout           = 30 # minutos; se passar disso, o job é interrompido (proteção contra gasto)

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.lake.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  # Parâmetros lidos pelo script: de onde ler o texto bruto e onde gravar o Parquet.
  default_arguments = {
    "--raw_path"     = "s3://${aws_s3_bucket.lake.id}/raw/cotahist/"
    "--curated_path" = "s3://${aws_s3_bucket.lake.id}/curated/cotahist/"
    "--enable-metrics" = "true"
  }
}

# ---------- Athena ----------
# "Database" aqui é só uma gaveta de organização no catálogo do Glue, onde a tabela do Athena será criada.
resource "aws_glue_catalog_database" "b3" {
  name = replace("${var.prefix}_b3", "-", "_")
}

# Workgroup = "configurações de uso" do Athena: onde salvar resultados e qual o limite por consulta.
resource "aws_athena_workgroup" "lab" {
  name          = "${var.prefix}-lab"
  force_destroy = true
  configuration {
    enforce_workgroup_configuration    = true
    bytes_scanned_cutoff_per_query     = 10737418240 # 10 GB por query: protege contra query cara
    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.id}/athena-results/"
    }
  }
}

# ---------- Alerta de custo ----------
# Se o gasto real do mês passar de 80% do limite (US$ 10 por padrão), manda um e-mail.
resource "aws_budgets_budget" "lab" {
  name         = "${var.prefix}-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}

# ---------- Saídas ----------
# Valores exibidos ao final do `terraform apply` (e lidos com `terraform output -raw <nome>`).
output "bucket" {
  value = aws_s3_bucket.lake.id  # nome do bucket criado
}
output "glue_job" {
  value = aws_glue_job.cotahist.name  # nome do job, para disparar com aws glue start-job-run
}
output "athena_workgroup" {
  value = aws_athena_workgroup.lab.name  # workgroup a selecionar no console do Athena
}
output "database" {
  value = aws_glue_catalog_database.b3.name  # database onde criar a tabela
}
