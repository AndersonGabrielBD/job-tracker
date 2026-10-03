"""Thin DynamoDB read/write helpers shared by the harvester and dashboard
Lambdas."""
import time

import boto3
from boto3.dynamodb.conditions import Attr, Key

GSI_PK_VALUE = "JOB"

_dynamodb = boto3.resource("dynamodb")


def _table(table_name):
    return _dynamodb.Table(table_name)


def filter_existing_ids(table_name, job_ids):
    """Return the subset of job_ids already present in the table, so the
    harvester never reprocesses a job it has already seen."""
    job_ids = list(job_ids)
    if not job_ids:
        return set()

    table_key_name = _table(table_name).table_name
    existing = set()
    for i in range(0, len(job_ids), 100):
        batch = job_ids[i:i + 100]
        request_items = {table_key_name: {"Keys": [{"job_id": jid} for jid in batch]}}
        while request_items:
            response = _dynamodb.meta.client.batch_get_item(RequestItems=request_items)
            for item in response.get("Responses", {}).get(table_key_name, []):
                existing.add(item["job_id"])
            request_items = response.get("UnprocessedKeys") or {}
    return existing


def write_jobs(table_name, jobs, ttl_seconds):
    if not jobs:
        return
    table = _table(table_name)
    ttl = int(time.time()) + ttl_seconds
    with table.batch_writer(overwrite_by_pkeys=["job_id"]) as batch:
        for job in jobs:
            item = dict(job)
            item["gsi_pk"] = GSI_PK_VALUE
            item["status"] = "new"
            item["ttl"] = ttl
            batch.put_item(Item=item)


def query_jobs(table_name, index_name, since_iso, limit=200):
    table = _table(table_name)
    response = table.query(
        IndexName=index_name,
        KeyConditionExpression=Key("gsi_pk").eq(GSI_PK_VALUE),
        FilterExpression=Attr("posted_at").gte(since_iso),
        ScanIndexForward=False,
        Limit=limit,
    )
    return response.get("Items", [])


def mark_applied(table_name, job_id, applied_at_iso):
    table = _table(table_name)
    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :applied, applied_at = :at",
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":applied": "applied", ":at": applied_at_iso},
    )
