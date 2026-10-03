import json

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_ssm as ssm,
)
from constructs import Construct

# Repo that hosts this CDK project's CI/CD pipeline (GitHub Actions).
CI_REPO = "AndersonGabrielBD/job-tracker"

PARAM_PREFIX = "/job-radar"
STACK_KEYWORDS_PARAM = f"{PARAM_PREFIX}/stack-keywords"
ADZUNA_APP_ID_PARAM = f"{PARAM_PREFIX}/adzuna-app-id"
ADZUNA_APP_KEY_PARAM = f"{PARAM_PREFIX}/adzuna-app-key"
JOOBLE_API_KEY_PARAM = f"{PARAM_PREFIX}/jooble-api-key"
DASHBOARD_TOKEN_PARAM = f"{PARAM_PREFIX}/dashboard-token"

# Baked into the stack since it's not sensitive -- edit here and redeploy to
# tune matching. [term, weight] pairs: CORE (3) is the actual day job stack,
# SECONDARY (2) is adjacent/strongly-related tech, NICE (1) is generic
# signal that alone shouldn't carry a match (e.g. "backend" appears in every
# posting regardless of language). A title hit counts 2x the weight.
_CORE = ["python", "fastapi", "flask", "celery", "sqlalchemy", "aws lambda", "lambda", "postgresql"]
_SECONDARY = [
    "aws", "ecs", "fargate", "sqs", "eventbridge", "s3", "cloudwatch",
    "django", "mysql", "supabase", "redis", "pandas", "polars", "numpy",
    "sql", "etl", "engenheiro de dados", "data engineer", "data engineering", "data pipeline",
    "docker", "pytest",
]
_NICE = ["react", "next.js", "tailwind", "typescript", "javascript", "github actions", "ci/cd", "backend", "rest api", "microservices"]

DEFAULT_STACK_KEYWORDS = (
    [[term, 3] for term in _CORE]
    + [[term, 2] for term in _SECONDARY]
    + [[term, 1] for term in _NICE]
)

GSI_NAME = "ScoreIndex"
TTL_DAYS = 50


class JobRadarStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Storage ---------------------------------------------------
        jobs_table = dynamodb.Table(
            self, "JobsTable",
            partition_key=dynamodb.Attribute(name="job_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN,
        )
        jobs_table.add_global_secondary_index(
            index_name=GSI_NAME,
            partition_key=dynamodb.Attribute(name="gsi_pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="match_score", type=dynamodb.AttributeType.NUMBER),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Non-sensitive config: managed by CDK directly.
        ssm.StringParameter(
            self, "StackKeywordsParam",
            parameter_name=STACK_KEYWORDS_PARAM,
            string_value=json.dumps(DEFAULT_STACK_KEYWORDS),
        )

        # Sensitive config (Adzuna/Jooble credentials, dashboard token):
        # CloudFormation cannot create SecureString SSM parameters, so these
        # are *not* CDK-managed resources -- populate them once after the
        # first deploy with:
        #   aws ssm put-parameter --type SecureString --name <name> --value <value>
        # The stack only grants IAM read access to the known parameter names.

        # --- Shared Lambda Layer ----------------------------------------
        common_layer = _lambda.LayerVersion(
            self, "CommonLayer",
            code=_lambda.Code.from_asset("lambda/common_layer"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        )

        # --- Harvester Lambda --------------------------------------------
        harvester_log_group = logs.LogGroup(
            self, "HarvesterLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        harvester_fn = _lambda.Function(
            self, "HarvesterFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambda/harvester"),
            layers=[common_layer],
            timeout=Duration.minutes(2),
            memory_size=256,
            log_group=harvester_log_group,
            environment={
                "TABLE_NAME": jobs_table.table_name,
                "TTL_DAYS": str(TTL_DAYS),
                "STACK_KEYWORDS_PARAM": STACK_KEYWORDS_PARAM,
                "ADZUNA_APP_ID_PARAM": ADZUNA_APP_ID_PARAM,
                "ADZUNA_APP_KEY_PARAM": ADZUNA_APP_KEY_PARAM,
                "JOOBLE_API_KEY_PARAM": JOOBLE_API_KEY_PARAM,
            },
        )
        jobs_table.grant_read_write_data(harvester_fn)
        self._grant_ssm_read(harvester_fn, [
            STACK_KEYWORDS_PARAM, ADZUNA_APP_ID_PARAM, ADZUNA_APP_KEY_PARAM, JOOBLE_API_KEY_PARAM,
        ])

        # --- Dashboard Lambda (Function URL) ------------------------------
        dashboard_log_group = logs.LogGroup(
            self, "DashboardLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
        )
        dashboard_fn = _lambda.Function(
            self, "DashboardFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambda/dashboard"),
            layers=[common_layer],
            timeout=Duration.seconds(10),
            memory_size=128,
            log_group=dashboard_log_group,
            environment={
                "TABLE_NAME": jobs_table.table_name,
                "GSI_NAME": GSI_NAME,
                "DASHBOARD_TOKEN_PARAM": DASHBOARD_TOKEN_PARAM,
            },
        )
        jobs_table.grant_read_write_data(dashboard_fn)  # read (list) + write (mark applied)
        self._grant_ssm_read(dashboard_fn, [DASHBOARD_TOKEN_PARAM])

        function_url = dashboard_fn.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
        )

        # --- Schedule: 2 runs/day -----------------------------------------
        # 08:00 and 18:00 America/Sao_Paulo (UTC-3, no DST) -> 11:00 and 21:00 UTC.
        schedules = {
            "Morning": ("11", "morning"),
            "Evening": ("21", "evening"),
        }
        for label, (hour, slot) in schedules.items():
            rule = events.Rule(
                self, f"HarvesterSchedule{label}",
                schedule=events.Schedule.cron(minute="0", hour=hour),
            )
            rule.add_target(
                targets.LambdaFunction(
                    harvester_fn,
                    retry_attempts=2,
                    event=events.RuleTargetInput.from_object({"run": slot}),
                )
            )

        # --- CI/CD: let GitHub Actions deploy this stack via OIDC ----------
        # The GitHub OIDC provider is account-global (created once by the
        # commits-automation stack) -- import it instead of re-declaring it.
        github_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            self, "ImportedGitHubOidcProvider",
            f"arn:aws:iam::{self.account}:oidc-provider/token.actions.githubusercontent.com",
        )

        ci_owner, ci_repo_name = CI_REPO.split("/")

        deploy_role = iam.Role(
            self, "GitHubActionsDeployRole",
            role_name="github-actions-cdk-deploy-job-radar",
            max_session_duration=Duration.hours(1),
            assumed_by=iam.FederatedPrincipal(
                github_provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": [
                            f"repo:{CI_REPO}:*",
                            f"repo:{ci_owner}@*/{ci_repo_name}@*:*",
                        ],
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-*"],
            )
        )

        CfnOutput(self, "DashboardUrl", value=function_url.url)
        CfnOutput(self, "DeployRoleArn", value=deploy_role.role_arn)

    def _grant_ssm_read(self, fn, param_names):
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParameters"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter{name}" for name in param_names],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["kms:Decrypt"],
                resources=["*"],
                conditions={"StringEquals": {"kms:ViaService": f"ssm.{self.region}.amazonaws.com"}},
            )
        )
