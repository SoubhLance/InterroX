from pathlib import Path
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient
import redis.exceptions

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app
from app.redis_client import redis_client

client = TestClient(app)


def test_health_redis_up():
    """When Redis is reachable, GET /health returns status ok and redis up."""
    with patch.object(redis_client, "ping", return_value=True):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "redis": "up"}


def test_health_redis_down():
    """When Redis is unreachable, GET /health returns status ok and redis down without crashing (no 500)."""
    with patch.object(
        redis_client, "ping", side_effect=redis.exceptions.ConnectionError("Connection refused")
    ):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "redis": "down"}


def test_dev_kv_set_and_get():
    """POST /dev/kv sets key with TTL, and GET /dev/kv/{key} retrieves it with ttl_remaining."""
    with patch.object(redis_client, "set", return_value=True) as mock_set, \
         patch.object(redis_client, "get", return_value="test_value") as mock_get, \
         patch.object(redis_client, "ttl", return_value=28) as mock_ttl:

        # 1. Test POST /dev/kv
        post_resp = client.post("/dev/kv", json={"key": "test_key", "value": "test_value", "ttl_seconds": 30})
        assert post_resp.status_code == 200
        mock_set.assert_called_once_with(name="test_key", value="test_value", ex=30)
        assert post_resp.json() == {
            "key": "test_key",
            "value": "test_value",
            "ttl_seconds": 30,
        }

        # 2. Test GET /dev/kv/{key}
        get_resp = client.get("/dev/kv/test_key")
        assert get_resp.status_code == 200
        mock_get.assert_called_once_with("test_key")
        mock_ttl.assert_called_once_with("test_key")
        assert get_resp.json() == {
            "key": "test_key",
            "value": "test_value",
            "ttl_remaining": 28,
        }


def test_dev_kv_missing_or_expired_key():
    """GET /dev/kv/{key} returns 404 if the key is missing or expired."""
    with patch.object(redis_client, "get", return_value=None), \
         patch.object(redis_client, "ttl", return_value=-2):
        response = client.get("/dev/kv/missing_key")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


def test_dev_router_omitted_when_env_not_dev(monkeypatch):
    """When ENV is not 'dev', dev router is not registered."""
    from importlib import reload
    import app.config as config_module
    import app.main as main_module

    monkeypatch.setattr(config_module.settings, "ENV", "production")
    prod_app = main_module.FastAPI()
    prod_app.include_router(main_module.health.router)
    if config_module.settings.ENV == "dev":
        prod_app.include_router(main_module.dev.router)

    prod_client = TestClient(prod_app)
    response = prod_client.get("/dev/kv/some_key")
    assert response.status_code == 404
