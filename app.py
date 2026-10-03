#!/usr/bin/env python3
import os

import aws_cdk as cdk

from job_radar.job_radar_stack import JobRadarStack


app = cdk.App()
JobRadarStack(app, "JobRadarStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    )

app.synth()
