"""Root conftest for pytest — registers custom markers."""



def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: tests requiring a real database")
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring full stack")


def pytest_addoption(parser):
    """Add --e2e flag."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E tests (requires docker compose stack)",
    )
