from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session", autouse=True)
def db() -> None:
    """Keep static proxy configuration tests independent from PostgreSQL."""


def test_nginx_uses_dedicated_cloudflare_tunnel_listener() -> None:
    config = (REPOSITORY_ROOT / "frontend" / "nginx.conf").read_text()

    assert "listen 8080;" in config
    assert "listen 8081;" in config
    assert config.count("if ($server_port = 8081)") == 3
    assert "$remote_addr ~" not in config
    assert config.count('proxy_set_header CF-Connecting-IP "";') == 3


def test_compose_exposes_only_tunnel_listener_on_loopback() -> None:
    compose = (REPOSITORY_ROOT / "compose.yml").read_text()

    assert '"127.0.0.1:8080:8081"' in compose
    assert '"127.0.0.1:8080:80"' not in compose
    assert "-frontend.loadbalancer.server.port=8080" in compose


def test_production_compose_does_not_expose_management_dashboards() -> None:
    base = (REPOSITORY_ROOT / "compose.yml").read_text()
    production = (REPOSITORY_ROOT / "compose.traefik.yml").read_text()
    local = (REPOSITORY_ROOT / "compose.override.yml").read_text()

    assert "\n  adminer:" not in base
    assert "traefik-dashboard" not in production
    assert "- --api\n" not in production
    assert "\n  adminer:" in local


def test_production_services_drop_privileges() -> None:
    compose = (REPOSITORY_ROOT / "compose.yml").read_text()
    dockerfile = (REPOSITORY_ROOT / "backend" / "Dockerfile").read_text()

    assert compose.count("read_only: true") >= 5
    assert compose.count("security_opt: [\"no-new-privileges:true\"]") >= 5
    assert compose.count("cap_drop: [ALL]") >= 5
    assert "USER appuser" in dockerfile
    assert "network_mode: none" in compose
