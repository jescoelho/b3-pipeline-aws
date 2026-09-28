# athena/ — consultando os dados com SQL

**Athena** é o serviço da AWS que responde perguntas em SQL diretamente sobre os arquivos Parquet guardados no S3. Não há banco de dados ligado: você paga só pela quantidade de dado que cada consulta lê (US$ 5 por TB). O arquivo desta pasta é [`queries.sql`](queries.sql), com 4 consultas para rodar em ordem.

## Antes de começar

1. A infraestrutura precisa existir (`terraform apply`, ver [`../terraform/README.md`](../terraform/README.md)).
2. O job do Glue precisa ter rodado, para que exista Parquet em `s3://<bucket>/curated/cotahist/`.
3. No console do Athena, selecione o **workgroup** criado pelo Terraform (`terraform output -raw athena_workgroup`). Ele define onde os resultados são salvos e o limite de 10 GB por consulta.

## O que trocar no arquivo

| Onde | Valor atual | Trocar por |
|---|---|---|
| Todas as consultas | Marcador `<DATABASE>` | O `database` do seu `terraform output -raw database` |
| Consulta 1 | Marcador `<BUCKET>` (aparece em dois lugares: `LOCATION` e `storage.location.template`) | O `bucket` do seu `terraform output -raw bucket` |

O nome do bucket contém o número da sua conta AWS, por isso o repositório guarda só os marcadores. Faça a troca na sua cópia local e não faça commit dela.

## O que cada consulta faz

| # | O que faz | O que observar |
|---|---|---|
| 1 | Cria a tabela `cotahist`. É só um "mapa" que aponta para os arquivos; nenhum dado é copiado, e apagar a tabela não apaga os arquivos. Usa *partition projection*, então o Athena deduz sozinho as pastas `ano=/mes=` | Rode uma vez. `IF NOT EXISTS` permite repetir sem erro |
| 2 | Top 20 papéis por volume em **março de 2020**, filtrando por `ano` e `mes` | Na aba de execução, veja **Data scanned**: só uma partição é lida |
| 3 | A mesma pergunta **sem** filtro de mês | O **Data scanned** sobe. Na rodada real foram 477,57 KB contra 5,35 MB (~11,5×) |
| 4 | Retorno diário e volatilidade anualizada de 21 pregões, por papel, em 2020 | Para PETR4, a volatilidade vai de ~12% (jan) a ~200% (mar), o crash da pandemia. Isso valida o pipeline |

## Por que filtrar por `ano` e `mes`

Os dados estão em pastas por ano e mês. Um filtro por essas colunas faz o Athena abrir só as pastas necessárias; sem o filtro, ele lê tudo e a consulta custa mais. É o mesmo efeito em qualquer volume, então em terabytes a diferença vira dinheiro de verdade.

## Se algo der errado

- **`Table not found` ou `Database not found`:** o nome do database na consulta não bate com o criado pelo Terraform, ou a Consulta 1 não foi executada.
- **Consulta retorna 0 linhas:** confira se o Glue gravou em `curated/cotahist/ano=.../mes=.../` e se o `ano` do filtro existe nos dados (o arquivo de teste é só de 2020).
- **`Access Denied`:** o bucket usado na consulta não é o seu, ou seu usuário não tem permissão de leitura nele.
- **Consulta cancelada pelo limite de 10 GB:** esperado como proteção de custo. Adicione filtro de `ano` e `mes`.
