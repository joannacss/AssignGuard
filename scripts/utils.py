"""
This module defines shared repository paths used by the AssignGuard scripts.
It centralizes data, example input, and results directories so command-line tools can share consistent defaults.
@Author: Joanna C. S. Santos
"""

from pathlib import Path

BASE_DIR: Path = Path(__file__).parent.parent
DATA_DIR: Path = BASE_DIR / "data"
EXAMPLE1_DATA_DIR: Path = DATA_DIR / "example1"
RESULTS_DIR: Path = BASE_DIR / "results"
