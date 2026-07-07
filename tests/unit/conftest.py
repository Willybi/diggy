"""sys.path setup for unit tests (pure Python, no DB required)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../server/api"))
