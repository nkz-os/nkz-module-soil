import boto3
from nkz_soil.config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY


def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
    )


def upload_cog(client, bucket: str, key: str, data: bytes, content_type: str = "image/tiff"):
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def generate_presigned_url(client, bucket: str, key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in,
    )
