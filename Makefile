.PHONY: test-fast test-regression test-integration

# Fast unit checks for local iteration
test-fast:
	python3 -m pytest -m "unit or not integration" tests/test_intent_policy.py tests/test_mcp_readonly_tools.py tests/test_llm_config.py

# Default regression suite (unit + non-AWS integration-safe tests)
test-regression:
	python3 -m pytest -m "not integration and not aws" tests

# Integration path (requires AWS/API credentials and environment setup)
test-integration:
	python3 -m pytest -m "integration or aws" tests/integration
