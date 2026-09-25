from __future__ import annotations

from core.config import load_settings
from observability.dashboard import build_dashboard


if __name__ == "__main__":
    print(f"Dashboard -> {build_dashboard(load_settings())}")
