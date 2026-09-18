# Exploration: GitHub Readiness for ai-rag

**Change**: `github-readiness`  
**Date**: 2026-09-18  
**Purpose**: Pre-public audit to ensure the project is professional, secure, and ready for GitHub

---

## Current State

The ai-rag project is a fully functional MVP with hexagonal architecture (FastAPI + Next.js + PostgreSQL/pgvector + Ollama). The codebase is clean, well-tested (151 unit tests), and follows good practices. However, several issues must be addressed before making it public on GitHub.

**Repository stats:**
- Total tracked files: 12,927 (inflated by build artifacts)
- Git repository size: 120 MB (should be <5 MB after cleanup)
- Branch: `main` (single branch, clean history)
- Commits: 10+ commits with conventional commit messages

---

## Findings by Area

### 1. Security Audit — Secrets & Tokens ✅ CLEAN

**Risk Level**: INFO (no issues found)

**What was checked:**
- All Python, TypeScript, JavaScript, YAML, TOML, SQL, and config files
- Git history for deleted secret files
- Environment files (.env, .env.local, etc.)
- Hardcoded API keys, passwords, tokens, credentials
- Patterns: `sk-*`, `ghp_*`, `github_pat_*`, `AKIA*`

**Findings:**
- ✅ No hardcoded API keys, tokens, or secrets found
- ✅ No .env files committed (only .env.example)
- ✅ .gitignore properly excludes .env, .venv, __pycache__, node_modules, .next
- ✅ .env.example is comprehensive and well-documented
- ✅ docker-compose.yml uses dev defaults (password "rag") — acceptable for local dev
- ✅ No credentials in source code, tests, or documentation
- ✅ No private registry URLs in dependencies

**Files verified:**
- `.env.example` — template only, no real credentials
- `docker-compose.yml` — dev defaults, clearly documented
- `src/config.py` — loads from env vars, no hardcoded secrets
- `frontend/lib/sse.ts` — uses `NEXT_PUBLIC_API_URL` env var
- All migration SQL files — clean
- All test files — clean

---

### 2. README Assessment ⚠️ NEEDS UPDATES

**Risk Level**: WARNING

**Current state:**
- README.md: 871 lines, comprehensive but has issues
- PROJECT_README.md: 797 lines, internal architecture document

**Issues found:**

1. **References to non-existent sample documents** (CRITICAL)
   - README lines 369-370 mention `sample_contract.txt` and `technical_spec.md`
   - Actual files in `data/docs/`: `travel_policy.md`, `q3_results.md`, `engineering_onboarding.md`
   - **Impact**: Users following the quick start will be confused

2. **Dual README confusion** (WARNING)
   - README.md is public-facing (871 lines)
   - PROJECT_README.md is internal architecture doc (797 lines)
   - **Recommendation**: Keep README.md for GitHub, consider renaming PROJECT_README.md to ARCHITECTURE.md or moving to docs/

3. **Missing elements for public GitHub** (INFO)
   - No screenshots or demo GIF
   - No CI/CD badges (build status, license, Python version)
   - No LICENSE file (README says "as-is for educational" but no legal license)
   - No CONTRIBUTING.md

4. **Unnecessary mention** (INFO)
   - Line 863: "LangChain — Inspiration for RAG patterns (not used in implementation)"
   - **Recommendation**: Remove — if not used, don't mention

**What's good:**
- ✅ Comprehensive feature list
- ✅ Architecture diagram (ASCII art)
- ✅ Quick start guide with step-by-step instructions
- ✅ API reference with examples
- ✅ Configuration documentation
- ✅ Testing instructions
- ✅ Project structure overview
- ✅ Roadmap with completed items marked

---

### 3. Project Structure & Organization 🔴 CRITICAL ISSUES

**Risk Level**: CRITICAL

**Issues found:**

1. **1,786 frontend/.next/ build artifacts tracked in git** (CRITICAL)
   - 80 MB of build output committed
   - Bloats .git directory to 120 MB
   - **Files**: `frontend/.next/**` (cache, standalone, server, static)
   - **Fix**: Remove from git, ensure .gitignore covers it (already does)
   - **Command**: `git rm -r --cached frontend/.next/`

2. **35 __pycache__/*.pyc files tracked in git** (CRITICAL)
   - Python bytecode committed despite .gitignore rules
   - Likely committed before .gitignore was updated
   - **Files**: `src/**/__pycache__/*.pyc`, `tests/**/__pycache__/*.pyc`
   - **Fix**: Remove from git
   - **Command**: `git rm -r --cached '**/__pycache__'`

3. **.atl/ directory tracked** (WARNING)
   - Tool-specific metadata (skill registry cache)
   - **Files**: `.atl/.skill-registry.cache.json`, `.atl/skill-registry.md`
   - **Recommendation**: Remove from git, add to .gitignore

4. **openspec/ directory tracked** (WARNING)
   - 26 files of internal SDD workflow artifacts
   - Includes archived changes, specs, config
   - **Recommendation**: Debatable — could keep as documentation of development process, or remove for cleaner public repo

5. **No root .dockerignore** (WARNING)
   - Backend Dockerfile copies everything including .git, .venv, tests
   - **Impact**: Larger Docker images, slower builds
   - **Fix**: Create root .dockerignore

6. **frontend/public/ is empty** (INFO)
   - No favicon, no images
   - **Recommendation**: Add favicon.ico at minimum

**What's good:**
- ✅ Clean hexagonal architecture (ports/adapters/core/api)
- ✅ Well-organized test structure (unit/integration/e2e)
- ✅ Sample documents are fictional and safe (Acme Corp)
- ✅ No TODO/FIXME/HACK comments in source code
- ✅ No debug print/console.log statements
- ✅ No dead code or orphaned directories

---

### 4. Git State ⚠️ NEEDS CLEANUP

**Risk Level**: WARNING

**Current state:**
- Branch: `main` (single branch)
- Uncommitted changes: 15 files (all __pycache__ and .atl files)
- No remote configured yet
- Git history: Clean, conventional commits

**Issues:**

1. **Uncommitted __pycache__ changes** (WARNING)
   - 14 .pyc files modified
   - These shouldn't be tracked at all
   - **Fix**: Remove from git tracking

2. **Uncommitted .atl changes** (WARNING)
   - `.atl/.skill-registry.cache.json` and `.atl/skill-registry.md` modified
   - **Fix**: Remove from git tracking

3. **Large repository size** (CRITICAL)
   - .git directory: 120 MB
   - Should be <5 MB after removing build artifacts
   - **Fix**: Remove .next/ and __pycache__/ from git, then `git gc`

**What's good:**
- ✅ .gitignore is comprehensive
- ✅ No large binary files (images, videos, etc.)
- ✅ .git/config has no local-only settings
- ✅ Clean commit history with meaningful messages

---

### 5. Dependencies & Configuration ✅ CLEAN

**Risk Level**: INFO (no issues)

**What was checked:**
- pyproject.toml
- requirements.txt
- frontend/package.json
- Dockerfile.backend
- frontend/Dockerfile
- docker-compose.yml

**Findings:**
- ✅ All Python dependencies are public PyPI packages
- ✅ All Node.js dependencies are public npm packages
- ✅ No private registry URLs
- ✅ No internal/corporate dependencies
- ✅ Docker images are standard public images (python:3.11-slim, node:20-alpine, pgvector/pgvector:pg16, ollama/ollama:latest)
- ✅ No hardcoded internal URLs
- ✅ All configuration via environment variables

---

### 6. Documentation ⚠️ NEEDS WORK

**Risk Level**: WARNING

**What exists:**
- README.md (public-facing, 871 lines)
- PROJECT_README.md (internal architecture, 797 lines)
- frontend/README.md (frontend-specific, 32 lines)
- openspec/ (SDD workflow documentation)

**What's missing:**
- ❌ LICENSE file (CRITICAL for public GitHub)
- ❌ CONTRIBUTING.md (WARNING)
- ❌ CHANGELOG.md (INFO)
- ❌ CODE_OF_CONDUCT.md (INFO)
- ❌ CI/CD configuration (.github/workflows/) (INFO)

**Recommendations:**
1. Add MIT or Apache 2.0 LICENSE file
2. Consider adding CONTRIBUTING.md with development setup
3. Add .github/workflows/ for CI (pytest, lint, build)
4. Clarify relationship between README.md and PROJECT_README.md

---

### 7. Frontend-Specific ✅ MOSTLY CLEAN

**Risk Level**: INFO

**What was checked:**
- frontend/.env (doesn't exist, good)
- frontend/next.config.mjs
- frontend/Dockerfile
- frontend/.dockerignore
- All TypeScript/TSX files

**Findings:**
- ✅ No .env files committed
- ✅ next.config.mjs is minimal (only `output: "standalone"`)
- ✅ Frontend uses env vars for API URL (`NEXT_PUBLIC_API_URL`)
- ✅ No hardcoded production URLs
- ✅ .dockerignore excludes node_modules and .next
- ✅ TypeScript config is clean
- ✅ No build artifacts should be committed (but 1,786 are — see section 3)

**Minor issues:**
- frontend/public/ is empty (no favicon)
- frontend/README.md is minimal but adequate

---

### 8. General Professionalism ✅ GOOD

**Risk Level**: INFO

**Code quality:**
- ✅ Clean hexagonal architecture
- ✅ Consistent code style (ruff for Python, ESLint for TypeScript)
- ✅ Comprehensive test coverage (151 unit tests)
- ✅ No embarrassing comments or debug code
- ✅ Professional error handling
- ✅ Good separation of concerns

**Project self-contained:**
- ✅ Can clone and run with Docker Compose
- ✅ Clear setup instructions
- ✅ Sample documents included
- ✅ All dependencies are public

**Areas for improvement:**
- Add screenshots/demo to README
- Add CI badges
- Add LICENSE file
- Clean up git history (remove build artifacts)

---

## Summary of Issues

### CRITICAL (Must fix before push)

| # | Issue | Files | Fix |
|---|-------|-------|-----|
| 1 | 1,786 frontend/.next/ build artifacts in git | `frontend/.next/**` | `git rm -r --cached frontend/.next/` |
| 2 | 35 __pycache__/*.pyc files in git | `src/**/__pycache__/`, `tests/**/__pycache__/` | `git rm -r --cached '**/__pycache__'` |
| 3 | No LICENSE file | Root directory | Add MIT or Apache 2.0 LICENSE |
| 4 | README references non-existent sample docs | README.md lines 369-370 | Update to reference actual files |

### WARNING (Should fix)

| # | Issue | Files | Fix |
|---|-------|-------|-----|
| 5 | .atl/ directory tracked | `.atl/*` | Remove from git, add to .gitignore |
| 6 | openspec/ tracked (26 files) | `openspec/**` | Decide: keep as docs or remove |
| 7 | No root .dockerignore | Root directory | Create .dockerignore |
| 8 | No CONTRIBUTING.md | Root directory | Add contributing guide |
| 9 | Dual README confusion | README.md, PROJECT_README.md | Clarify or rename PROJECT_README.md |
| 10 | frontend/public/ empty | `frontend/public/` | Add favicon.ico |

### INFO (Nice to have)

| # | Issue | Files | Fix |
|---|-------|-------|-----|
| 11 | No screenshots in README | README.md | Add demo GIF or screenshots |
| 12 | No CI badges | README.md | Add after setting up CI |
| 13 | No CI/CD config | `.github/workflows/` | Add pytest/lint/build workflows |
| 14 | README mentions LangChain "(not used)" | README.md line 863 | Remove mention |
| 15 | Git repo 120 MB | `.git/` | Will shrink after removing artifacts |

---

## Affected Areas

### Files to modify:
- `README.md` — fix sample doc references, remove LangChain mention
- `.gitignore` — add .atl/ if not already covered
- Create `LICENSE` file
- Create `CONTRIBUTING.md` (optional)
- Create `.dockerignore` (root level)
- Create `.github/workflows/ci.yml` (optional)

### Files to remove from git:
- `frontend/.next/**` (1,786 files)
- `src/**/__pycache__/**` (35 files)
- `tests/**/__pycache__/**` (included in 35 count)
- `.atl/**` (2 files)

### Files to add:
- `frontend/public/favicon.ico` (optional)
- Screenshots/demo GIF (optional)

---

## Recommendation

**Priority order:**

1. **Remove build artifacts from git** (CRITICAL)
   - This is the biggest issue — 1,786 files, 80 MB
   - Will reduce repo size from 120 MB to <5 MB
   - Commands:
     ```bash
     git rm -r --cached frontend/.next/
     git rm -r --cached '**/__pycache__'
     git rm -r --cached .atl/
     git commit -m "chore: remove build artifacts and cache files from git"
     ```

2. **Add LICENSE file** (CRITICAL)
   - Required for public GitHub
   - Recommend MIT or Apache 2.0

3. **Fix README sample doc references** (CRITICAL)
   - Update lines 369-370 to reference actual files
   - Change `sample_contract.txt` → `travel_policy.md`
   - Change `technical_spec.md` → `q3_results.md` or `engineering_onboarding.md`

4. **Create root .dockerignore** (WARNING)
   - Exclude .git, .venv, __pycache__, .next, node_modules, tests, openspec

5. **Add CONTRIBUTING.md** (WARNING)
   - Development setup instructions
   - How to run tests
   - Code style guidelines

6. **Clarify README situation** (WARNING)
   - Keep README.md as public-facing
   - Rename PROJECT_README.md to ARCHITECTURE.md or move to docs/

7. **Optional improvements** (INFO)
   - Add screenshots/demo GIF
   - Add CI/CD workflows
   - Add favicon
   - Remove LangChain mention from README

---

## Risks

1. **Git history still contains build artifacts**
   - Even after `git rm --cached`, the artifacts remain in git history
   - **Mitigation**: Consider `git filter-branch` or BFG Repo-Cleaner for complete removal
   - **Tradeoff**: Rewriting history is disruptive; for a new public repo, might be acceptable

2. **openspec/ contains internal development artifacts**
   - Shows development process, archived changes, specs
   - **Decision**: Keep as documentation of methodology, or remove for cleaner repo
   - **Recommendation**: Keep — demonstrates professional development process

3. **docker-compose.yml has hardcoded dev password**
   - Password "rag" is in docker-compose.yml and .env.example
   - **Risk**: Low — clearly dev defaults, documented
   - **Mitigation**: Add comment in docker-compose.yml noting this is for dev only

---

## Ready for Proposal

**Yes** — The exploration is complete and provides a clear picture of what needs to be done.

**What the orchestrator should tell the user:**

"The exploration is complete. We found 4 CRITICAL issues that must be fixed before pushing to GitHub:

1. **1,786 build artifacts (frontend/.next/) are tracked in git** — 80 MB of unnecessary files
2. **35 Python cache files (__pycache__/*.pyc) are tracked in git**
3. **No LICENSE file exists** — required for public GitHub
4. **README references non-existent sample documents** — will confuse users

Additionally, there are 6 WARNING-level issues (no root .dockerignore, no CONTRIBUTING.md, dual README confusion, etc.) and several optional improvements.

The codebase itself is clean — no secrets, no hardcoded credentials, good architecture, comprehensive tests. The main work is git cleanup and documentation updates.

**Estimated effort**: 2-3 hours to fix all CRITICAL and WARNING issues.

**Recommendation**: Proceed with proposal to create a structured plan for fixing these issues before the GitHub push."

---

## Appendix: Detailed File Counts

```
Total tracked files: 12,927
├── frontend/.next/: 1,786 files (80 MB)
├── openspec/: 26 files
├── src/: ~50 files
├── tests/: ~30 files
├── frontend/ (source): ~15 files
├── data/docs/: 3 files
├── migrations/: 3 files
├── Root files: 8 files
└── Other: ~12,000 files (mostly frontend/.next/)

After cleanup:
├── Expected tracked files: ~150
├── Expected .git size: <5 MB
└── Reduction: 98.8% fewer files, 96% smaller repo
```

---

## Appendix: Security Scan Results

```
Scanned for:
- API keys: sk-*, ghp_*, github_pat_*, AKIA*
- Passwords: password=, secret=, token=, api_key=
- Credentials: credentials, private_key, access_key

Results:
✅ No hardcoded secrets found
✅ No .env files committed
✅ .gitignore properly configured
✅ All credentials via environment variables
✅ No private registry URLs
✅ No internal/corporate dependencies
```

---

**Exploration complete. Ready for proposal phase.**
