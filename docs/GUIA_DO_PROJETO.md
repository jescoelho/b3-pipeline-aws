# Guia do projeto: o que cada pasta, arquivo e função faz

Este guia é para quem **não** é da área de dados. Ele responde, na ordem em que as coisas acontecem: *o que entra, o que acontece no meio, o que sai e por que cada peça existe*. Para uma explicação mais conceitual (por que particionar, por que Parquet, etc.), veja também [`ESTUDO.md`](ESTUDO.md).

---

## 1. Em uma frase

O projeto pega um **arquivo de texto enorme e difícil de ler** publicado pela bolsa de valores brasileira (B3), com todas as negociações de ações de um ano, e o transforma numa **tabela organizada que se consulta em milissegundos**, primeiro no computador local e depois na nuvem da Amazon (AWS).

## 2. A analogia da fábrica

| Etapa da fábrica | No projeto | Onde está |
|---|---|---|
| **Matéria-prima** | Arquivo de texto da B3 (`COTAHIST`) | `data/raw/` (baixado por `scripts/`) |
| **Manual de montagem** | Mapa "qual posição do texto = qual informação" | `src/cotahist/fields.py` |
| **Máquina de corte** | Lê o texto e separa cada informação | `src/cotahist/parser.py` |
| **Embalagem e estoque** | Guarda em arquivos Parquet organizados por ano/mês | `src/cotahist/pipeline.py` (local) ou `glue/` (nuvem) |
| **Galpão** | Armazenamento na nuvem (S3) | criado por `terraform/` |
| **Balcão de atendimento** | Consultas em SQL (Athena) | `athena/queries.sql` |
| **Controle de qualidade** | Testes automáticos | `tests/` |
| **Fábrica de amostras** | Dados falsos para treinar sem risco | `src/cotahist/synthetic.py` |

## 3. Fluxo completo, passo a passo

```
 B3 publica um .ZIP por ano
        │  (1) scripts/download_cotahist.sh baixa e descompacta
        ▼
 data/raw/COTAHIST_A2020.TXT        ← texto bruto, 245 caracteres por linha
        │  (2) parser: corta cada linha nas posições certas e converte tipos
        │      ├─ local:  src/cotahist/pipeline.py  (seu computador)
        │      └─ nuvem:  glue/cotahist_to_parquet.py (várias máquinas em paralelo)
        ▼
 curated/cotahist/ano=2020/mes=3/…parquet   ← dados prontos, separados por mês
        │  (3) Athena lê só as pastas necessárias
        ▼
 Resultado de consultas SQL (ex.: volatilidade da PETR4 em 2020)
```

### Passo 1 — Obter o dado bruto
A B3 publica todo ano um `.ZIP` com o "histórico de cotações": para cada ação e cada dia de negociação, o preço de abertura, máximo, mínimo, fechamento, quantidade e volume financeiro. O script `scripts/download_cotahist.sh` baixa e descompacta esse arquivo em `data/raw/`.

### Passo 2 — Interpretar o texto (parser)
O arquivo não tem vírgulas nem colunas: cada linha tem **exatamente 245 caracteres** e o significado de cada trecho depende da posição. Por exemplo, os caracteres 13–24 são o código da ação (`PETR4`), e `0000000002790` nas posições 57–69 significa R$ 27,90 (o ponto decimal é omitido). O parser aplica essas regras e produz uma tabela comum.

### Passo 3 — Gravar em formato eficiente e organizado
A tabela é gravada em **Parquet**, formato pensado para análise (compacto, lê só as colunas pedidas), e separada em **pastas por ano e mês** (`ano=2020/mes=3/`). Quem pergunta sobre março abre uma pasta em vez de doze.

### Passo 4 — Fazer isso em escala, na nuvem
No computador, processar 235 mil linhas leva segundos. Para bilhões de linhas, usa-se o **AWS Glue**, que divide o trabalho entre várias máquinas. A lógica é a mesma; muda só quem executa.

### Passo 5 — Consultar
O **Athena** permite escrever perguntas em SQL diretamente sobre os arquivos guardados na nuvem, sem manter um banco de dados ligado. A cobrança é por quantidade de dado lido, e por isso o particionamento economiza dinheiro (na rodada real: ~11,5× menos dado lido).

### Passo 6 — Validar com a realidade
A prova de que tudo funciona: a volatilidade calculada da PETR4 sobe de ~12% (janeiro/2020) para ~200% (março/2020), coincidindo com o crash da pandemia. Um parser com erro produziria ruído, não um evento reconhecível.

---

## 4. Mapa de pastas e arquivos

```
b3-pipeline-aws/
├── README.md                     Visão geral e comandos para rodar (voltado a quem já é técnico)
├── pytest.ini                    Configuração dos testes (diz onde está o código e os testes)
├── .gitignore                    Lista o que NÃO deve ir para o Git (dados, estado do Terraform, caches)
├── docs/
│   ├── GUIA_DO_PROJETO.md        Este documento
│   └── ESTUDO.md                 Explicação conceitual em linguagem simples + exercício + glossário
├── scripts/
│   └── download_cotahist.sh      Baixa e descompacta o arquivo anual da B3
├── src/cotahist/                 O código Python que roda no seu computador
│   ├── __init__.py               Marca a pasta como pacote Python
│   ├── fields.py                 O mapa de posições (manual de montagem)
│   ├── parser.py                 Transforma texto em tabela
│   ├── pipeline.py               Grava a tabela em Parquet, por ano/mês
│   └── synthetic.py              Gera arquivos falsos no formato da B3
├── tests/
│   └── test_cotahist.py          Verificações automáticas
├── glue/
│   └── cotahist_to_parquet.py    Mesma lógica do parser/pipeline, versão em escala (nuvem)
├── terraform/
│   └── main.tf                   "Receita" que cria toda a infraestrutura na AWS
├── athena/
│   └── queries.sql               Consultas SQL de exemplo
└── data/                         (criada ao rodar; fora do Git)
    ├── raw/                      Arquivos de texto originais
    └── curated/                  Parquet pronto (organizado por ano/mês)
```

> **Sobre "raw" e "curated":** são nomes de convenção em engenharia de dados. *Raw* ("cru") é o dado exatamente como chegou, intocado, para poder reprocessar se algo der errado. *Curated* ("tratado") é o dado limpo, tipado e pronto para uso.

---

## 5. Cada arquivo em detalhe

### `src/cotahist/fields.py` — o mapa
- **`RECORD_LEN = 245`**: tamanho esperado de cada linha. Serve de alarme: linha com outro tamanho indica arquivo corrompido ou layout alterado.
- **`FIELDS`**: lista com 26 campos, cada um descrito por *(nome, posição inicial, posição final, tipo)*. Os tipos são: `s` texto, `i` inteiro, `p2` decimal com 2 casas implícitas (÷100), `p6` decimal com 6 casas (÷1.000.000), `d` data `AAAAMMDD`.
- **`COLSPECS` / `NAMES`**: as mesmas informações reformatadas para outras bibliotecas.

### `src/cotahist/parser.py` — a máquina de corte
| Função | O que faz, em linguagem simples |
|---|---|
| `_conv(raw, kind)` | Converte **um pedaço** de texto. `"0000000002790"` com tipo `p2` vira `27.90`; data `99991231` vira "sem data"; texto vazio vira "sem valor". |
| `parse_line(line)` | Converte **uma linha inteira** num dicionário `{campo: valor}`. Ignora cabeçalho (`00`) e rodapé (`99`) e recusa linhas com tamanho diferente de 245. |
| `iter_records(lines)` | Percorre muitas linhas e entrega só as cotações válidas, uma a uma, sem carregar tudo na memória. |
| `read_cotahist(path)` | Lê o arquivo completo (codificação `latin-1`, que entende acentos), devolve uma tabela e cria as colunas `ano` e `mes`. |

### `src/cotahist/pipeline.py` — embalagem local
| Função | O que faz |
|---|---|
| `run(raw_files, out_dir)` | Para cada arquivo de entrada: lê com o parser → converte para formato Parquet → grava nas pastas `ano=…/mes=…`. Devolve quantas linhas processou e quanto tempo levou. Reexecutar substitui as partições existentes, sem duplicar dados. |
| bloco `if __name__ == "__main__"` | Permite chamar pela linha de comando com `--raw` (entrada) e `--out` (saída). |

### `src/cotahist/synthetic.py` — fábrica de amostras
| Função | O que faz |
|---|---|
| `_fmt(kind, width, value)` | Formata um valor no jeito da B3 (o inverso de `_conv`): `27.90` → `0000000002790`. |
| `build_record(values)` | Monta uma linha completa de 245 caracteres a partir de um dicionário. |
| `_business_days(start, end)` | Lista os dias úteis (segunda a sexta) num período. Não considera feriados. |
| `generate(path, start, end, n_tickers, seed)` | Cria o arquivo inteiro com papéis e preços inventados (variação diária ao acaso de ~2%). A `seed` fixa o sorteio para que o resultado seja sempre igual, o que permite testes reproduzíveis. **Não use para análise financeira.** |

### `tests/test_cotahist.py` — controle de qualidade
| Teste | O que garante |
|---|---|
| `test_field_layout_is_contiguous_and_245` | O mapa não tem buracos nem sobreposições e soma exatamente 245 caracteres. |
| `test_roundtrip_single_record` | Monta uma linha da PETR4, passa pelo parser e confere se preço, data, volume e quantidade voltam corretos. |
| `test_header_trailer_skipped_and_bad_length_raises` | Cabeçalho/rodapé são ignorados; linha de tamanho errado gera erro (em vez de gravar dado errado em silêncio). |
| `test_pipeline_end_to_end` | Gera dados falsos, roda o pipeline inteiro, consulta o resultado e confere: nenhuma linha perdida, pastas por mês criadas, e preço máximo nunca menor que o mínimo. |

Para rodar: `python -m pytest` na raiz do projeto.

### `glue/cotahist_to_parquet.py` — versão em escala (nuvem)
Roda no AWS Glue com Spark. Passos internos:
1. **Preparação** — recebe os caminhos de entrada/saída e liga o motor Spark.
2. **Leitura** — lê o texto bruto do S3 e descarta cabeçalho/rodapé.
3. **Corte e conversão** — três funções auxiliares fazem o mesmo papel do parser: `s()` (texto), `p()` (número com casas implícitas), `d()` (data).
4. **Gravação** — cria `ano`/`mes` e grava o Parquet particionado. Antes de gravar, agrupa os dados por ano/mês para evitar o "problema dos arquivos pequenos" (centenas de arquivos minúsculos deixam consultas lentas).

> ⚠️ **Manutenção:** este script e `fields.py` contêm o mesmo layout, escrito duas vezes. Se um mudar, o outro precisa mudar junto.

### `terraform/main.tf` — a receita da infraestrutura
| Bloco | O que cria | Por que existe |
|---|---|---|
| `variable` (`region`, `prefix`, `budget_email`, `budget_usd`) | Parâmetros | Você informa seu prefixo e e-mail ao rodar. |
| `aws_s3_bucket` + `public_access_block` + `encryption` | O "HD na nuvem", privado e criptografado | Guarda dados brutos, prontos, scripts e resultados. |
| `aws_s3_object.glue_script` | Envia o script do Glue ao bucket | O Glue executa a partir dali. |
| `aws_iam_role` + políticas | Identidade e permissões do Glue | Ninguém (nem robôs) tem acesso por padrão; o Glue só pode mexer neste bucket. |
| `aws_glue_job` | O job cadastrado (2 máquinas pequenas, limite de 30 min) | Limites de tamanho e tempo funcionam como teto de custo. |
| `aws_glue_catalog_database` | "Gaveta" onde a tabela do Athena é registrada | Organização do catálogo. |
| `aws_athena_workgroup` | Configuração do Athena, com limite de 10 GB lidos por consulta | Protege contra uma consulta descuidada e cara. |
| `aws_budgets_budget` | Alerta por e-mail aos 80% de US$ 10/mês | Evita surpresas na fatura. |
| `output` (`bucket`, `glue_job`, …) | Valores mostrados ao final | Usados nos comandos seguintes. |

Comandos: `terraform apply` cria tudo; `terraform destroy` apaga tudo (**faça isso ao terminar para não pagar por recursos parados**).

### `athena/queries.sql` — as consultas
1. **Cria a tabela**: um "mapa" que diz ao Athena onde estão os arquivos e quais colunas têm — não copia nenhum dado. Usa *partition projection*: o Athena deduz sozinho as pastas `ano/mes`.
2. **Consulta com filtro de mês**: top 20 papéis por volume em março/2020. Lê só uma pasta.
3. **A mesma consulta sem filtro**: lê tudo. Compare o campo *Data scanned* das duas.
4. **Volatilidade de 21 dias**: mede o quanto o preço de cada papel oscila, anualizada. É a consulta que revela o crash de março/2020.

> ℹ️ O arquivo usa os marcadores `<BUCKET>` e `<DATABASE>`. Antes de rodar, troque-os pelos valores exibidos por `terraform output`. Como o nome do bucket contém o número da sua conta AWS, faça a troca só na sua cópia local e não a envie ao Git.

### `scripts/download_cotahist.sh`
Para cada ano informado (`./scripts/download_cotahist.sh 2020 2021`), baixa o `.ZIP` da B3 e o descompacta em `data/raw/`. A URL já mudou no passado; se falhar, confira no site da B3.

---

## 6. Como executar, do zero

**Local (sem custo, sem AWS):**
1. `pip install pandas pyarrow duckdb pytest`
2. `python -m pytest` — confirma que tudo está correto.
3. `./scripts/download_cotahist.sh 2020` — baixa o dado real (ou use `synthetic.py` para dado falso).
4. `PYTHONPATH=src python -m cotahist.pipeline --raw data/raw/COTAHIST_A2020.TXT --out data/curated/cotahist`

**Na nuvem (custo baixo, mas real):**
1. `cd terraform && terraform init && terraform apply -var prefix=SEUNOME-b3lab -var budget_email=seu@email`
2. Enviar o `.TXT` para `s3://<bucket>/raw/cotahist/`.
3. Disparar o job: `aws glue start-job-run --job-name <nome do job>`.
4. Abrir o Athena, rodar `athena/queries.sql`.
5. **`terraform destroy`** ao terminar.

---

## 7. Glossário

- **B3:** a bolsa de valores do Brasil.
- **COTAHIST:** arquivo anual de "cotações históricas" publicado pela B3.
- **Pregão:** dia de negociação na bolsa.
- **Ticker / código de negociação:** código curto de uma ação (`PETR4`).
- **Largura fixa:** formato de texto em que cada campo ocupa sempre as mesmas posições, sem separadores.
- **Parser:** programa que interpreta um texto e o transforma em dados estruturados.
- **Parquet:** formato de arquivo por colunas, compacto e rápido para análise.
- **Partição:** subpasta que separa os dados por um critério (aqui, ano e mês) para que consultas leiam só o necessário.
- **S3:** armazenamento de arquivos na nuvem da AWS.
- **Glue:** serviço da AWS que roda tarefas de transformação de dados em várias máquinas.
- **Spark / PySpark:** motor que divide um processamento grande entre várias máquinas.
- **Athena:** serviço da AWS que consulta arquivos do S3 com SQL, cobrando pelo dado lido.
- **SQL:** linguagem padrão para consultar dados.
- **IAM / Role:** sistema de permissões da AWS / identidade que um serviço assume para poder agir.
- **Terraform:** ferramenta que cria infraestrutura na nuvem a partir de um arquivo de descrição.
- **Volatilidade:** medida do quanto o preço de um ativo oscila.
- **Dado sintético:** dado inventado, com o formato do real, usado para testes.
