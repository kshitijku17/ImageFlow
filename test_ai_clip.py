"""Backward-compatible entry point for test_ai_clip.py (main test located in tests/test_ai_clip.py)."""
import sys
from tests.test_ai_clip import run_test

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
