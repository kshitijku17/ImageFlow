"""Backward-compatible entry point for test_ai_full_integration.py (main test located in tests/test_ai_full_integration.py)."""
import sys
from tests.test_ai_full_integration import run_full_integration_tests

if __name__ == "__main__":
    success = run_full_integration_tests()
    sys.exit(0 if success else 1)
