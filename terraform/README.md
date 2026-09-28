# terraform/ — criando (e destruindo) a infraestrutura na AWS

**Terraform** é uma ferramenta que cria recursos na nuvem a partir de um arquivo de descrição, em vez de cliques manuais no console. Aqui, o arquivo é [`main.tf`](main.tf). Cada bloco dele está comentado; este README explica como usá-lo com segurança.

## O que é criado

| Recurso | Para quê |
|---|---|
| Bucket S3 (privado, criptografado) | Guarda o dado bruto (`raw/`), o dado pronto (`curated/`), o script do Glue e os resultados do Athena |
| Role IAM do Glue | Permissão para o Glue mexer **só** neste bucket |
| Job Glue (2 workers, timeout 30 min) | Converte o texto da B3 em Parquet particionado |
| Database do catálogo + workgroup Athena (limite de 10 GB por consulta) | Onde as consultas SQL rodam |
| Budget (padrão US$ 10/mês) | E-mail de alerta quando o gasto passa de 80% |

## Pré-requisitos

- Conta AWS com MFA no usuário root e um usuário IAM/SSO com permissão de administrador.
- AWS CLI autenticado (`aws configure sso`).
- Terraform 1.5 ou superior.

## Como usar

```bash
cd terraform
terraform init                                  # baixa o provedor da AWS (uma vez)
terraform plan  -var prefix=SEUNOME-b3lab -var budget_email=seu@email   # mostra o que SERIA criado
terraform apply -var prefix=SEUNOME-b3lab -var budget_email=seu@email   # cria de verdade
```

Variáveis:

| Nome | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `prefix` | sim | — | Prefixo do nome do bucket. Nomes de bucket são únicos no mundo todo; o Terraform acrescenta o número da sua conta para evitar colisão |
| `budget_email` | sim | — | E-mail que recebe o alerta de custo |
| `budget_usd` | não | `10` | Teto mensal em dólares |
| `region` | não | `us-east-1` | Região da AWS |

Ao final, `terraform output` mostra `bucket`, `glue_job`, `athena_workgroup` e `database`. Use `terraform output -raw <nome>` para pegar um valor em scripts. Os próximos passos (enviar o `.TXT`, disparar o job, consultar no Athena) estão no [README principal](../README.md).

## Ao terminar: destruir tudo

```bash
terraform destroy -var prefix=SEUNOME-b3lab -var budget_email=seu@email
```

Isso apaga **todos** os recursos, inclusive os dados dentro do bucket (o `main.tf` usa `force_destroy = true` por ser um laboratório). Não deixe rodando: o Glue e o Athena cobram por uso e o S3 cobra por armazenamento.

## Cuidados

- **`terraform.tfstate`** (criado nesta pasta) é o "caderno" em que o Terraform anota o que criou. Não apague nem edite: sem ele, o Terraform perde o controle dos recursos e o `destroy` deixa de funcionar. Contém detalhes da sua conta, por isso está no `.gitignore` (assim como `.terraform/` e `*.tfvars`). **Nunca faça commit desses arquivos.**
- Ao usar outra conta ou outro `prefix`, o nome do bucket muda. Use o novo nome no lugar de `<BUCKET>` em [`athena/queries.sql`](../athena/queries.sql).
- Revise sempre o `terraform plan` antes do `apply`.
- O script do Glue é enviado ao bucket a partir de [`../glue/cotahist_to_parquet.py`](../glue/cotahist_to_parquet.py). Se você alterá-lo, rode `terraform apply` de novo para reenviar.
