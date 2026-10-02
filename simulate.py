"""Runs games without the web interface:  python simulate.py --seeds 1 2 3 --turns 300"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from server.sim.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
