"""Backward-compatible entry point for test_ai_indexing.py (main test located in tests/test_ai_indexing.py)."""
import sys
from tests.test_ai_indexing import run_indexing_test

if __name__ == "__main__":
    success = run_indexing_test()
    sys.exit(0 if success else 1)
