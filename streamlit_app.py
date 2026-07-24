"""Sevah Streamlit entry point."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from sevah.ui import render_app  # noqa: E402

render_app()

