from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "stress"
BASE_URL = "http://127.0.0.1:8765"


def request(path: str, payload: dict | None = None, method: str = "GET") -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    pdfs = [
        FIXTURES / "vector_pid_package_32.pdf",
        FIXTURES / "cable_continuation_package.pdf",
        FIXTURES / "raster_scanned_pid_package.pdf",
    ]
    missing = [str(path) for path in pdfs if not path.exists()]
    if missing:
        raise SystemExit(f"Missing stress fixtures: {missing}. Run scripts/generate-stress-fixtures.py first.")

    project = request("/projects", {"name": "Stress Fixture API Smoke"}, "POST")
    request(f"/projects/{project['id']}/imports", {"paths": [str(path) for path in pdfs]}, "POST")
    job_id = request(f"/projects/{project['id']}/jobs/extract", {}, "POST")["jobId"]

    for _ in range(300):
        status = request(f"/jobs/{job_id}")
        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            raise SystemExit(status["error"])
        time.sleep(0.2)
    else:
        raise SystemExit("Stress extraction timed out")

    graph = request(f"/projects/{project['id']}/graph")
    xlsx = request(f"/projects/{project['id']}/exports/xlsx", {}, "POST")
    svg = request(f"/projects/{project['id']}/exports/svg", {}, "POST")
    result = {
        "projectId": project["id"],
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "reviewItems": len(graph["reviewItems"]),
        "xlsx": xlsx["path"],
        "svg": svg["path"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
