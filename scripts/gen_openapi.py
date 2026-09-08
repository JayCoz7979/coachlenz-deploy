"""
Regenerate backend/openapi.json from the live FastAPI app.

    python -m scripts.gen_openapi        (from the repo root, with backend deps installed)

The committed backend/openapi.json is the machine-readable API description agents read
without a person. It can also be pulled from the running service at GET /openapi.json.
"""
import json
import pathlib


def main() -> None:
    from backend.main import app
    spec = app.openapi()
    out = pathlib.Path(__file__).resolve().parents[1] / "backend" / "openapi.json"
    out.write_text(json.dumps(spec), encoding="utf-8")
    print(f"wrote {out} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
