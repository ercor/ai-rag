# Contributing to AI RAG

Thank you for your interest in contributing! This document explains how to get involved.

## Reporting Bugs

Open a GitHub issue with:
- A clear title and description
- Steps to reproduce the problem
- Expected vs actual behavior
- Environment details (OS, Docker version, RAM)

## Suggesting Features

Open a GitHub issue with the `enhancement` label. Describe:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Development Setup

See the [Quick Start Guide](README.md#-quick-start-guide) in the README for full setup instructions.

```bash
git clone <repository-url>
cd ai-rag
cp .env.example .env
docker compose up -d --build
```

## Code Style

- **Python**: Formatted with [Ruff](https://docs.astral.sh/ruff/) (linter and formatter). Run `ruff check .` and `ruff format .` before committing.
- **TypeScript**: Formatted with ESLint and Prettier. Run `npm run lint` in the `frontend/` directory.
- **Tests**: Run `pytest tests/unit/ -v` before pushing. All tests must pass.

## Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`: `git checkout -b feat/your-feature`
3. Make your changes with clear, focused commits
4. Ensure tests pass and code is formatted
5. Push to your fork and open a Pull Request against `main`
6. Describe what your PR changes and why

Keep PRs focused — one feature or fix per PR.

## License

By contributing, you agree that your contributions will be licensed under the [GPL v3 License](LICENSE).
