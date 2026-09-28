# Como o pipeline B3 → AWS funciona, explicado em linguagem simples

Este documento explica o que foi construído e por que cada peça existe, sem assumir conhecimento prévio de engenharia de dados. É para revisar antes de avançar para as próximas semanas do roteiro.

## O quadro geral

Você construiu uma linha de montagem de dados. Ela pega um arquivo de texto bagunçado, sem separadores, e termina como uma tabela que se consulta em milissegundos, na nuvem, gastando centavos.

```
Texto de largura fixa (B3)
  → parser corta posições e tipa os campos
  → grava em Parquet, particionado por ano/mês
  → Glue faz isso em escala, na nuvem, em paralelo
  → Athena lê só as partições necessárias, cobrando por isso
  → o resultado bate com um evento real conhecido (validação)
```

Vamos abrir cada peça.

---

## 1. O dado bruto: o arquivo COTAHIST

A B3 disponibiliza um arquivo de texto puro, sem vírgula, sem tabulação — cada linha tem **exatamente 245 caracteres**, e cada trecho da linha significa uma coisa diferente. Por exemplo, os caracteres de 13 a 24 são sempre o código do papel (`PETR4`, `VALE3`...), os de 57 a 69 são o preço de abertura, escrito sem ponto decimal (`0000000002790` significa R$ 27,90).

Isso é chamado de **formato de largura fixa** (*fixed-width*). Era o padrão de sistemas dos anos 80-90, quando espaço em disco era caro e separadores como vírgula desperdiçavam bytes. A B3 nunca trocou esse formato — é assim até hoje.

**Onde isso vive no código:** `src/cotahist/fields.py` é literalmente um mapa: "essa faixa de caracteres = esse campo, desse tipo".

## 2. O parser: transformando texto em dado utilizável

Ler `0000000002790` e saber que isso é `27.90` não é automático — alguém precisa escrever a regra. É isso que `src/cotahist/parser.py` faz: pega a linha, corta nas posições certas, e converte cada pedaço para o tipo certo (número, data, texto).

Isso é o trabalho mais chato e mais importante de qualquer pipeline de dados: **ninguém confia em dado sem saber exatamente como ele foi interpretado**. Por isso existe o `tests/test_cotahist.py` — ele monta um registro artificial, manda pro parser, e confere se o que voltou bate com o que foi colocado. Se algum dia alguém mudar o layout sem querer, o teste quebra na hora, não seis meses depois quando alguém perceber que os preços estão errados.

## 3. Por que particionar: pastas em vez de um arquivo gigante

Depois de parseado, o dado vira **Parquet** — um formato onde as colunas ficam guardadas juntas (diferente do texto, onde as linhas ficam juntas). Isso importa porque a maioria das consultas não usa todas as colunas: se você só quer `preco_ultimo`, o banco lê só essa coluna, ignorando o resto.

Mas o ganho maior que você viu na prática foi outro: **particionamento**. Em vez de um arquivo `cotahist_2020.parquet` gigante, o dado foi separado em pastas: `ano=2020/mes=1/`, `ano=2020/mes=2/`, etc. Isso significa que quando você pergunta "me dê março de 2020", o sistema nem abre as outras 11 pastas — ele já sabe que a resposta só pode estar em `mes=3/`.

**É exatamente isso que os números que você mediu provam:**

| Consulta | Dados verificados | Tempo de execução |
|---|---|---|
| Com filtro `ano=2020 AND mes=3` | 477,57 KB | 616 ms |
| Sem filtro de partição | 5,35 MB | 2.487 s |

A proporção (~11,5x menos dado) bate exatamente com o número de partições (12 meses). Não é coincidência, é o mecanismo funcionando como projetado.

## 4. Glue: o mesmo trabalho do parser, só que "espalhado"

O `parser.py` roda no seu computador, uma linha de cada vez, sequencialmente. Isso é ótimo para 235 mil linhas (levou 14 segundos), mas ficaria impraticável para bilhões de linhas — um computador só, processando uma linha por vez, levaria dias.

O **AWS Glue** roda o mesmo tipo de lógica (veja em `glue/cotahist_to_parquet.py` que os comandos são quase idênticos: cortar a linha, converter tipo), só que usando **Spark**, que divide o arquivo em pedaços e processa vários pedaços ao mesmo tempo, em várias máquinas. Você configurou 2 "workers" — 2 máquinas trabalhando em paralelo. Para escalar de verdade (bilhões de linhas), aumentaria esse número, não mudaria a lógica.

**O que rodou de fato:** você subiu o arquivo real de 2020 para o S3 (o "HD na nuvem"), disparou o job, e em poucos minutos ele leu o texto bruto e escreveu de volta, já particionado, em Parquet. Rodou de primeira — sinal de que a lógica do parser local e do script Glue estavam bem alinhadas.

## 5. Por que o Glue precisa de uma "IAM Role"

Uma dúvida comum: por que o job Glue precisa de uma permissão especial (a `aws_iam_role.glue` no Terraform)? Porque o Glue não é você — é um robô rodando em nome da AWS. Sem essa permissão explícita, ele não teria autorização para ler o arquivo bruto no S3 nem para escrever o resultado de volta. É o mesmo princípio do usuário `je-admin`: ninguém, nem processo automático, tem acesso por padrão — cada um recebe só o que precisa.

## 6. Athena: consultar sem precisar "ligar" um banco de dados

Diferente de um banco tradicional (que fica ligado o tempo todo, cobrando por isso), o **Athena** só existe no momento da consulta. Ele lê os arquivos Parquet direto do S3, responde, e "desliga". Por isso a cobrança é por **dado escaneado**, não por tempo ligado — daí a importância do particionamento: menos dado escaneado, menos custo.

A tabela criada no Athena (`CREATE EXTERNAL TABLE`) não copia dado nenhum — é só um **mapa** dizendo "os dados estão em tal pasta do S3, organizados assim". A "partition projection" configurada é o que permite ao Athena calcular sozinho quais pastas existem (por ano/mês), sem precisar escanear o S3 inteiro só para descobrir isso.

## 7. A prova final: a volatilidade da PETR4

O teste mais forte de que tudo funcionou não foi nenhum número técnico — foi o resultado bater com a realidade. A fórmula de volatilidade (variação dos retornos diários, numa janela de 21 dias, anualizada) é padrão em finanças. Ao rodar para PETR4 em 2020, a volatilidade saltou de ~12% em janeiro para ~200% em março — exatamente quando o petróleo despencou e a B3 acionou *circuit breakers* várias vezes na mesma semana. Um pipeline com erro no parser (datas trocadas, preços mal convertidos) não produziria esse padrão coerente — produziria ruído.

---

## Exercício para fixar

Pegue uma linha qualquer do arquivo real (`data/raw/COTAHIST_A2020.TXT`) e, com calculadora na mão:

1. Conte manualmente os caracteres 13 a 24 — deve ser um código de papel válido.
2. Conte os caracteres 57 a 69 — divida o número por 100. Isso deveria ser o preço de abertura daquele dia.
3. Rode `parse_line()` nessa mesma linha (em um script Python simples) e compare com o que você calculou à mão.

Se bater, você entendeu o mecanismo — não só decorou o resultado.

## Glossário rápido

- **Largura fixa (fixed-width):** formato onde cada campo ocupa sempre a mesma posição na linha, sem separador.
- **Parquet:** formato de arquivo colunar, feito para ser lido rápido e ocupar pouco espaço.
- **Particionamento:** organizar os dados em pastas por algum critério (aqui, ano/mês) para que consultas leiam só o necessário.
- **IAM Role:** uma identidade que um serviço da AWS (não uma pessoa) assume para ter permissão de fazer algo.
- **Athena:** ferramenta de consulta que lê arquivos direto do S3, sem precisar de um banco de dados ligado o tempo todo.
- **Data scanned:** quantidade de dado que uma consulta precisou ler para responder — é a base da cobrança do Athena.
