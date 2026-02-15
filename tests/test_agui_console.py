import json
import pytest
from fastapi.testclient import TestClient

import boto3
import requests

from bin.agui_server import app


class DummySTS:
    def __init__(self):
        self.assumed_args = None

    def assume_role(self, RoleArn, RoleSessionName, DurationSeconds):
        self.assumed_args = dict(RoleArn=RoleArn, RoleSessionName=RoleSessionName, DurationSeconds=DurationSeconds)
        return {
            "Credentials": {
                "AccessKeyId": "AKIAFAKEASSUME",
                "SecretAccessKey": "FAKESECRET",
                "SessionToken": "FAKETOKEN"
            }
        }

    def get_session_token(self, DurationSeconds):
        return {
            "Credentials": {
                "AccessKeyId": "AKIAFAKE",
                "SecretAccessKey": "FAKESECRET",
                "SessionToken": "FAKETOKEN"
            }
        }


class DummyResponse:
    def __init__(self, token="fake-token"):
        self._token = token

    def raise_for_status(self):
        return None

    def json(self):
        return {"SigninToken": self._token}


@pytest.fixture(autouse=True)
def patch_boto_and_requests(monkeypatch):
    """Patch boto3.client('sts') and requests.get to avoid hitting real AWS."""
    dummy = DummySTS()

    def fake_boto_client(name, *args, **kwargs):
        if name == "sts":
            return dummy
        # Fall back to real client for other services if needed
        return boto3.client(name, *args, **kwargs)

    def fake_requests_get(url, params=None, timeout=None):
        # Basic validation of expected params
        assert params is not None
        assert params.get("Action") == "getSigninToken"
        assert "Session" in params
        return DummyResponse(token="unit-test-token")

    monkeypatch.setattr(boto3, "client", fake_boto_client)
    monkeypatch.setattr(requests, "get", fake_requests_get)
    yield


def test_console_url_without_role():
    client = TestClient(app)
    resp = client.post("/api/aws/console")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success") is True
    assert "url" in body
    assert "SigninToken=unit-test-token" in body["url"]


def test_console_url_with_role():
    client = TestClient(app)
    payload = {"role_arn": "arn:aws:iam::123456789012:role/TestRole", "duration_seconds": 900}
    resp = client.post("/api/aws/console", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success") is True
    assert "url" in body
    assert "SigninToken=unit-test-token" in body["url"]
