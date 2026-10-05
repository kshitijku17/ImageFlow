"""Backward-compatible entry point for test_ai_date_filter.py (main test located in tests/test_ai_date_filter.py)."""
import sys
from tests.test_ai_date_filter import run_date_filtering_tests

if __name__ == "__main__":
    success = run_date_filtering_tests()
    sys.exit(0 if success else 1)
