from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_nginx_uses_dedicated_cloudflare_tunnel_listener() -> None:
    config = (REPOSITORY_ROOT / "frontend" / "nginx.conf").read_text()

    assert "listen 80;" in config
    assert "listen 8081;" in config
    assert config.count("if ($server_port = 8081)") == 3
    assert "$remote_addr ~" not in config
    assert config.count('proxy_set_header CF-Connecting-IP "";') == 3


def test_compose_exposes_only_tunnel_listener_on_loopback() -> None:
    compose = (REPOSITORY_ROOT / "compose.yml").read_text()

    assert '"127.0.0.1:8080:8081"' in compose
    assert '"127.0.0.1:8080:80"' not in compose
    assert "-frontend.loadbalancer.server.port=80" in compose
