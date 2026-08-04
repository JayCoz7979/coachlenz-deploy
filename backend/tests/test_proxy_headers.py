"""Finding #11: the per-IP rate limiter collapses to one global bucket unless
uvicorn is told to trust the platform proxy's forwarded client IP. Guard the
start commands so the flags can't silently drop off."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_dockerfile_enables_proxy_headers():
    cmd = _read("backend/Dockerfile")
    assert "--proxy-headers" in cmd
    assert "--forwarded-allow-ips" in cmd


def test_railway_start_enables_proxy_headers():
    cfg = _read("backend/railway.toml")
    assert "--proxy-headers" in cfg
    assert "--forwarded-allow-ips" in cfg
