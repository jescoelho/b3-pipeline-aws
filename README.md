# Pipeline B3 (COTAHIST) na AWS — laboratório de treino

Objetivo: treinar um pipeline de dados de volume na AWS com a série histórica da B3.

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

## Roteiro de evolução
1. Semana 1: este repositório rodando ponta a ponta com 1 ano; meça linhas, tempo, GB escaneados.
2. Semana 2: 10+ anos (mais arquivos); orquestrar com Step Functions (crawl -> job -> teste de qualidade); idempotência e reprocesso por partição.
3. Semana 3: escale (dados sintéticos maiores ou vários anos); tuning do Spark (nº de partições, tamanho dos arquivos de saída ~128-512 MB); registre custo por escala.
4. Semana 4: qualidade (Glue Data Quality: volume, nulos, `preco_maximo >= preco_minimo`, freshness), IaC completo, streaming opcional (Kinesis -> Firehose).

## Avisos honestos
- O layout de `src/cotahist/fields.py` foi escrito a partir do layout oficial da B3, mas **confira contra o PDF que acompanha o download** e rode o parser num arquivo real; os testes usam dados sintéticos gerados pelo mesmo layout (validam consistência interna, não a fidelidade ao arquivo real).
- `glue/cotahist_to_parquet.py` e `terraform/main.tf` **não foram executados** (sem AWS/Spark aqui). Espere ajustes no primeiro `apply`/execução.
- Confira a URL de download no site da B3; ela já mudou no passado.
- Custo: 2 workers G.1X, timeout 30 min, Athena limitado a 10 GB/consulta, Budget com alerta. Ainda assim, cheque o Billing e rode `terraform destroy`.
