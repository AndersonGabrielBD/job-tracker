import aws_cdk as core
import aws_cdk.assertions as assertions

from job_radar.job_radar_stack import JobRadarStack


def _synth_template():
    app = core.App()
    stack = JobRadarStack(
        app, "job-radar-test",
        env=core.Environment(account="123456789012", region="us-east-1"),
    )
    return assertions.Template.from_stack(stack)


def test_dynamodb_table_with_gsi():
    template = _synth_template()
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "KeySchema": [{"AttributeName": "job_id", "KeyType": "HASH"}],
    })


def test_two_lambda_functions():
    template = _synth_template()
    template.resource_count_is("AWS::Lambda::Function", 2)


def test_two_eventbridge_schedule_rules():
    template = _synth_template()
    template.resource_count_is("AWS::Events::Rule", 2)


def test_dashboard_has_function_url():
    template = _synth_template()
    template.resource_count_is("AWS::Lambda::Url", 1)
    template.has_resource_properties("AWS::Lambda::Url", {"AuthType": "NONE"})
