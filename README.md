# Pipeline B3 (COTAHIST) na AWS — laboratório de treino

Objetivo: treinar um pipeline de dados de volume na AWS com a série histórica da B3.

> **Não é da área de dados?** Comece por [`docs/GUIA_DO_PROJETO.md`](docs/GUIA_DO_PROJETO.md) (o que cada pasta, arquivo e função faz, passo a passo) e depois [`docs/ESTUDO.md`](docs/ESTUDO.md) (os conceitos).

```
B3 (COTAHIST .TXT, posição fixa, 245 bytes)
  -> S3 raw/
  -> Glue (PySpark)  -> S3 curated/ (Parquet particionado ano/mes)
  -> Athena (partition projection)
```

## Fase 0 — local, sem AWS (faça primeiro)
```bash
pip install pandas pyarrow duckdb pytest
python -m pytest                                   # valida layout + parser + pipeline
PYTHONPATH=src python -m cotahist.synthetic --start 2010-01-01 --end 2020-12-31 --tickers 500 --out data/raw/SINT.TXT
PYTHONPATH=src python -m cotahist.pipeline --raw data/raw/SINT.TXT --out data/curated/cotahist
```
Depois baixe dados reais (na sua máquina): `./scripts/download_cotahist.sh 2020 2021 2022`
e rode o pipeline em `data/raw/COTAHIST_A*.TXT`.

Exercício: consulte com DuckDB e compare o tempo lendo o TXT vs. o Parquet
(`select ... from read_parquet('data/curated/cotahist/**/*.parquet', hive_partitioning=true) where ano=2020`).

## Fase 1 — AWS (quando a conta estiver pronta)
Pré-requisitos: MFA no root, usuário IAM/SSO admin, AWS CLI configurado (`aws configure sso`), Terraform >= 1.5.
```bash
cd terraform
terraform init
terraform apply -var prefix=SEUNOME-b3lab -var budget_email=seu@email
BUCKET=$(terraform output -raw bucket)
aws s3 cp ../data/raw/COTAHIST_A2020.TXT s3://$BUCKET/raw/cotahist/
aws glue start-job-run --job-name $(terraform output -raw glue_job)
```
Depois, no console do Athena (workgroup criado pelo Terraform), rode `athena/queries.sql`
(troque `<BUCKET>` e `<DATABASE>`). Compare "Data scanned" entre a consulta 2 (com partição) e a 3 (sem).

**Ao terminar: `terraform destroy`.**

## Resultados (rodada real, ano 2020, COTAHIST_A2020.TXT)

Pipeline testado ponta a ponta na AWS com o arquivo real de 2020 da B3 (não sintético).

**Glue job:** rodou com sucesso na primeira tentativa (2 workers G.1X), gerando 12 partições
mensais em Parquet (2-4 MB cada, ~35 MB no total).

**Athena — efeito do particionamento** (mesma consulta, com e sem filtro de partição):

| Consulta | Dados verificados | Tempo de execução |
|---|---|---|
| `WHERE ano=2020 AND mes=3` (com partição) | 477,57 KB | 616 ms |
| Sem filtro de partição (ano todo) | 5,35 MB | 2.487 s |

Filtrar por partição escaneou **~11,5x menos dado** (proporcional a 1 de 12 partições) e rodou
**~4x mais rápido**. Em escala de gigabytes/terabytes essa mesma proporção é a diferença entre
uma consulta de centavos e uma de dezenas de dólares no Athena (cobrança de US$ 5/TB escaneado).

**Validação analítica — volatilidade anualizada de PETR4 em 2020** (janela móvel de 21 dias):
a volatilidade sobe de ~11-13% em janeiro para um pico de ~200% entre 25/mar e 06/abr — exatamente
o período do crash da pandemia e dos circuit breakers na B3 — depois normaliza gradualmente para
~55-60% em maio. O pipeline reproduz um evento de mercado real e conhecido, o que valida o parser
e a lógica ponta a ponta (não só a consistência interna testada com dados sintéticos).

**Custo:** infraestrutura completa (S3, Glue, Athena, Budget) rodada e testada permanecendo dentro
do free tier / créditos, com gasto real desprezível (a rodada inteira do case não chegou a
consumir de forma perceptível o teto de US$ 10 configurado no Budget).

## Roteiro de evolução
1. Semana 1: este repositório rodando ponta a ponta com 1 ano; meça linhas, tempo, GB escaneados.
2. Semana 2: 10+ anos (mais arquivos); orquestrar com Step Functions (crawl -> job -> teste de qualidade); idempotência e reprocesso por partição.
3. Semana 3: escale (dados sintéticos maiores ou vários anos); tuning do Spark (nº de partições, tamanho dos arquivos de saída ~128-512 MB); registre custo por escala.
4. Semana 4: qualidade (Glue Data Quality: volume, nulos, `preco_maximo >= preco_minimo`, freshness), IaC completo, streaming opcional (Kinesis -> Firehose).

## Avisos honestos
- O layout de `src/cotahist/fields.py` foi escrito a partir do layout oficial da B3. Já foi validado contra um arquivo real (COTAHIST_A2020.TXT) com resultado coerente (ver seção Resultados), mas se usar outro ano/formato, confira contra o PDF de layout que acompanha o download.
- `glue/cotahist_to_parquet.py` e `terraform/main.tf` já rodaram com sucesso em conta AWS real (ver Resultados). Mesmo assim, revise o `terraform plan` antes de aplicar em outra conta — nomes de bucket e valores de budget são específicos do ambiente de quem criou o repositório.
- Confira a URL de download no site da B3; ela já mudou no passado.
- Custo: 2 workers G.1X, timeout 30 min, Athena limitado a 10 GB/consulta, Budget com alerta e Budget Action (bloqueio automático via IAM policy em 100% do gasto real). Ainda assim, cheque o Billing e rode `terraform destroy` ao terminar.
