from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app import auth as auth_module
from app.config import Settings, get_settings
from app.storage import Storage

TEST_JWT_SECRET = "test-secret-at-least-32-characters-long-0123456789"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def settings() -> Settings:
    os.environ.setdefault("APP_ENV", "test")
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    os.environ["STORAGE_BUCKET"] = "cornelius-test"
    os.environ["STORAGE_REGION"] = "eu-central-1"
    os.environ["STORAGE_ENDPOINT_URL"] = "https://s3.eu-central-1.amazonaws.com"
    os.environ["STORAGE_ACCESS_KEY_ID"] = "testing"
    os.environ["STORAGE_SECRET_ACCESS_KEY"] = "testing"
    os.environ.setdefault(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54329/cornelius_test"
    )
    get_settings.cache_clear()
    auth_module.reset_verifier()
    return get_settings()


@pytest.fixture
def storage(settings: Settings) -> Iterator[Storage]:
    """A Storage instance backed by moto's in-memory S3."""
    with mock_aws():
        client = boto3.client("s3", region_name=settings.storage_region)
        client.create_bucket(
            Bucket=settings.storage_bucket,
            CreateBucketConfiguration={"LocationConstraint": settings.storage_region},
        )
        yield Storage(settings=settings, client=client)


def make_token(user_id: uuid.UUID, email: str = "surgeon@example.org", aal: str = "aal1") -> str:
    return auth_module.mint_test_token(TEST_JWT_SECRET, user_id, email, aal)
