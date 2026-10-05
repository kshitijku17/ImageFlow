"""Backward-compatible entry point for test_ai_search.py (main test located in tests/test_ai_search.py)."""
import sys
from tests.test_ai_search import run_search_tests

if __name__ == "__main__":
    success = run_search_tests()
    sys.exit(0 if success else 1)
