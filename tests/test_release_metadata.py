from __future__ import annotations

import json
from pathlib import Path

from pygate import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_zenodo_version_matches_package_version():
    metadata = json.loads((ROOT / ".zenodo.json").read_text())

    assert metadata["version"] == __version__
