# Engineering Onboarding Guide

## Welcome

Welcome to the Engineering team! This guide covers everything you need to know for your first week.

## Development Environment

All engineers use macOS or Linux. Required tools:
- Git (latest stable)
- Docker Desktop
- VS Code or JetBrains IDE
- Node.js 20 LTS
- Python 3.11+

## Code Standards

All code must pass linting before merge. We use:
- Python: ruff for linting and formatting
- TypeScript: ESLint + Prettier
- Go: gofmt + golangci-lint

Pull requests require at least one approval from a team member. CI must pass before merging.

## Architecture Overview

We follow hexagonal architecture (ports and adapters). Key principles:
- Dependencies point inward toward the domain
- External services are behind port interfaces
- Business logic has no framework dependencies
- Adapters are swappable via configuration

## Deployment

Applications are deployed via Docker containers to Kubernetes. The CI/CD pipeline:
1. Run tests (unit + integration)
2. Build container image
3. Push to registry
4. Deploy to staging (automatic)
5. Deploy to production (manual approval)

## Communication

- Slack: #engineering for general questions
- Weekly architecture review: Thursdays at 2pm
- Sprint planning: bi-weekly on Mondays
- Incident response: PagerDuty (rotation schedule on wiki)
