import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


def ensure_upload_dir() -> str:
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def upload_file_object(object_key: str, contents: bytes, content_type: str) -> str:
    if settings.aws_s3_bucket:
        client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        try:
            client.put_object(Bucket=settings.aws_s3_bucket, Key=object_key, Body=contents, ContentType=content_type)
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError("Failed to upload file to S3") from exc
        return object_key

    upload_dir = ensure_upload_dir()
    path = os.path.join(upload_dir, object_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handler:
        handler.write(contents)
    return path


def get_download_url(object_key: str) -> str:
    if settings.aws_s3_bucket:
        client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        return client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": settings.aws_s3_bucket, "Key": object_key},
            ExpiresIn=settings.s3_signed_url_expire_seconds,
        )

    return object_key
