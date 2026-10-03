# job-radar

Busca vagas de emprego automaticamente 2x/dia, pontua cada uma por overlap de keywords com a
stack de backend/Python/AWS, e deixa tudo num dashboard web pessoal pra só olhar o score e
clicar no link de aplicar. Custo-alvo: ~$0/mês.

## Como funciona

- **AWS CDK** (Python) provisiona tudo em [`job_radar/job_radar_stack.py`](job_radar/job_radar_stack.py).
- A **Harvester Lambda** ([`lambda/harvester/handler.py`](lambda/harvester/handler.py)) busca
  vagas em 6 fontes (Remotive, RemoteOK, Arbeitnow, Adzuna, Gupy, Jooble), filtra por escopo
  (remoto em qualquer lugar, ou Brasil remoto/presencial em Maceió), deduplica contra o que já
  foi visto, pontua por overlap de keywords (sem LLM, zero custo) e grava no DynamoDB.
- Duas **EventBridge rules** disparam a harvester às 08:00 e 18:00 (America/Sao_Paulo).
- A **Dashboard Lambda** ([`lambda/dashboard/handler.py`](lambda/dashboard/handler.py)), exposta
  via **Function URL**, renderiza uma tabela HTML com as vagas ordenadas por score, protegida
  por um token secreto na query string (`?token=...`). Tem um botão "Mark Applied" por vaga.
- Lógica compartilhada entre as duas Lambdas vive numa **Lambda Layer**
  (`lambda/common_layer/python/job_radar_common/`).
- **GitHub Actions** deploya via OIDC (sem chaves AWS de longa duração) — reaproveita o mesmo
  padrão do repo `commits-automation`, inclusive importando o mesmo GitHub OIDC provider
  (que é único por conta AWS).

## Primeiro deploy (precisa ser local)

O deploy via GitHub Actions usa uma IAM Role que esse próprio stack cria — então o primeiro
`cdk deploy` precisa rodar localmente com suas credenciais AWS:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cdk bootstrap   # só se a conta/região ainda não foi bootstrapped
cdk deploy
```

Anote os outputs `DashboardUrl` e `DeployRoleArn`.

## Configurar o deploy via GitHub Actions

1. No repositório GitHub, crie a variável de repositório `AWS_DEPLOY_ROLE_ARN` com o valor do
   output `DeployRoleArn` do deploy local.
2. A partir daí, todo push em `main` dispara `cdk deploy` automaticamente; PRs rodam
   `cdk synth` + `cdk diff`.

## Popular as credenciais (SecureString via SSM)

CloudFormation não consegue criar parâmetros `SecureString` (limitação da própria AWS), então
esses valores são configurados manualmente uma vez, fora do CDK:

```powershell
aws ssm put-parameter --type SecureString --name /job-radar/adzuna-app-id   --value "<seu app_id>"
aws ssm put-parameter --type SecureString --name /job-radar/adzuna-app-key  --value "<seu app_key>"
aws ssm put-parameter --type SecureString --name /job-radar/jooble-api-key  --value "<sua api key>"
aws ssm put-parameter --type SecureString --name /job-radar/dashboard-token --value "<um token aleatorio longo>"
```

- Adzuna: crie uma conta grátis em https://developer.adzuna.com/ pra pegar `app_id`/`app_key`.
- Jooble: cadastre-se em https://jooble.org/api/about pra pegar a API key gratuita.
- Dashboard token: qualquer string longa e aleatória (ex: `openssl rand -hex 32`). Guarde-a —
  é o que você vai colar na URL do dashboard pra acessar.

A lista de keywords da stack (`/job-radar/stack-keywords`) **é** gerenciada pelo CDK
(`DEFAULT_STACK_KEYWORDS` em `job_radar_stack.py`) — pra ajustar o matching, edite a lista no
código e rode `cdk deploy` de novo.

## Usar o dashboard

Abra `<DashboardUrl>?token=<seu dashboard-token>` no navegador. Dá pra trocar a janela de dias
visível com `&days=30`. Salve nos favoritos.

## Desenvolvimento local

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pytest
cdk synth
cdk diff
cdk deploy
```

## Comandos úteis

* `cdk ls` — lista os stacks do app
* `cdk synth` — emite o template CloudFormation sintetizado
* `cdk deploy` — deploya este stack na conta/região configurada
* `cdk diff` — compara o stack deployado com o estado atual
