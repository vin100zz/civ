"""Starts the game server:  python run.py [--port 8005]  then open http://127.0.0.1:8005"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from server.main import main  # noqa: E402

if __name__ == "__main__":
    main()
