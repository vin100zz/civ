"""Entry point: python -m server.main [--port 8005]  (run from the src/ directory)."""
from __future__ import annotations

import argparse
import socket
import sys

import uvicorn

from .api.app import create_app
from .engine.rules.loader import ConfigError


def main() -> None:
    parser = argparse.ArgumentParser(description="Civilization server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)
    args = parser.parse_args()
    try:
        app = create_app()
    except ConfigError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    if not _port_is_free(args.host, args.port):
        print(f"Port {args.port} is already in use: another server (maybe this game) is "
              f"running there.\nClose it, or choose another port: python run.py --port 8006",
              file=sys.stderr)
        sys.exit(1)
    print(f"Civilization: open http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


if __name__ == "__main__":
    main()
