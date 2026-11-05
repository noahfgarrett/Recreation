from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except Exception as exc:
        print(f"uvicorn is required to run the service: {exc}", file=sys.stderr)
        return 2
    os.environ["RECREATION_DATA_DIR"] = str(Path(args.data_dir).resolve())
    uvicorn.run(
        "recreation_extractor.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recreation-extractor")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_parser = sub.add_parser("serve", help="Run the local extraction API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--data-dir", default=".recreation-data")
    serve_parser.add_argument("--log-level", default="info")
    serve_parser.set_defaults(func=serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
