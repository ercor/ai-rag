# Tasks: GitHub Readiness for ai-rag

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700 (600 from GPL v3 license text + ~100 actual changes) |
| 400-line budget risk | Medium (license boilerplate inflates count; reviewable code changes are ~100 lines) |
| Chained PRs recommended | No (all changes are tightly coupled — orphan squash depends on everything) |
| Suggested split | Single PR with `size:exception` |
| Delivery strategy | auto-chain |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Full github-readiness: untrack artifacts, add license, fix docs, docker hygiene, favicon, orphan squash | PR 1 (size:exception) | `git ls-files \| grep -E '(frontend/\.next\|__pycache__\|\.atl/)' \| wc -l` → expect 0 | `docker compose config` validates YAML; `docker compose build --dry-run` (if supported) or `docker compose build backend` smoke test | Full revert via `git revert HEAD` on the squash commit; all files restorable |

Rationale for single PR: Phase 3 (orphan branch squash) collapses all prior changes into one commit. Splitting into chained PRs would require intermediate states that don't exist after the squash. The ~600 lines from GPL v3 are non-reviewable boilerplate. Actual reviewable diff is ~100 lines.

## Phase 1: Git Cleanup (Sequential)

Remove build artifacts from git tracking. These must run in order because each `git rm --cached` stages deletions that accumulate toward the final commit.

- [ ] **T01** Add `.atl/` to `.gitignore`
  - **File**: `.gitignore`
  - **Action**: Append `.atl/` entry under a new `# Tools` section at the end of the file
  - **Detail**: Add after line 28 (after the `data/docs/*.docx` line). Add a blank line, then `# Tools` comment, then `.atl/`
  - **Depends on**: Nothing
  - **Effort**: Small
  - **Verification**: `grep -q '^\.atl/$' .gitignore` returns 0

- [ ] **T02** Untrack `frontend/.next/` build artifacts from git index
  - **Command**: `git rm -r --cached frontend/.next/`
  - **Detail**: Removes ~1786 files from git tracking. Files remain on disk. The `frontend/.next/` pattern is already in `.gitignore` so they won't be re-tracked.
  - **Depends on**: Nothing (can run in parallel with T01)
  - **Effort**: Small (single command, but large output)
  - **Verification**: `git ls-files --cached frontend/.next/ | wc -l` returns 0

- [ ] **T03** Untrack all `__pycache__/` directories from git index
  - **Command**: `git rm -r --cached '**/__pycache__'` (or `git ls-files --cached | grep '__pycache__' | xargs git rm --cached`)
  - **Detail**: Removes ~35 `.pyc` files from tracking. `__pycache__/` is already in `.gitignore`.
  - **Depends on**: Nothing (can run in parallel with T01, T02)
  - **Effort**: Small
  - **Verification**: `git ls-files --cached | grep '__pycache__' | wc -l` returns 0

- [ ] **T04** Untrack `.atl/` tool metadata from git index
  - **Command**: `git rm -r --cached .atl/`
  - **Detail**: Removes 2 files from tracking. Depends on T01 being done first so `.atl/` is in `.gitignore` before untracking (prevents accidental re-add).
  - **Depends on**: T01 (must have `.atl/` in `.gitignore` first)
  - **Effort**: Small
  - **Verification**: `git ls-files --cached .atl/ | wc -l` returns 0

## Phase 2: File Changes (Parallel)

All tasks in this phase are independent of each other and can be done in any order.

- [ ] **T05** Create `LICENSE` file with GPL v3 full text
  - **File**: `LICENSE` (new file at repo root)
  - **Action**: Create the file with the full GNU General Public License v3.0 text. Standard license, available from https://www.gnu.org/licenses/gpl-3.0.txt
  - **Detail**: The file should contain the complete GPL v3 license text. No customization needed — it's a standard license.
  - **Depends on**: Nothing
  - **Effort**: Small (copy-paste standard text)
  - **Verification**: `test -f LICENSE && head -1 LICENSE | grep -q 'GNU GENERAL PUBLIC LICENSE'`

- [ ] **T06** Fix README.md broken references and remove LangChain mention
  - **File**: `README.md`
  - **Action**: Four edits required:
    1. **Line 369**: Change `data/docs/sample_contract.txt` → `data/docs/travel_policy.md` and update description from "Example contract" → "Example travel policy"
    2. **Line 370**: Change `data/docs/technical_spec.md` → `data/docs/q3_results.md` and update description from "Example technical specification" → "Example quarterly results"
    3. **Line 483**: Change `sample_contract.txt` → `travel_policy.md` in citation example
    4. **Lines 497-498**: Change `technical_spec.md` → `q3_results.md` in both citation entries
    5. **Line 863**: Remove the entire LangChain bullet line: `- **LangChain** - Inspiration for RAG patterns (not used in implementation)`
  - **Depends on**: Nothing
  - **Effort**: Small
  - **Verification**: `grep -c 'sample_contract\|technical_spec\|LangChain' README.md` returns 0

- [ ] **T07** Rename `PROJECT_README.md` → `ARCHITECTURE.md`
  - **Command**: `git mv PROJECT_README.md ARCHITECTURE.md`
  - **Detail**: Use `git mv` to preserve history. No content changes needed. Verified that no files outside `openspec/` reference `PROJECT_README.md`, so no link updates required.
  - **Depends on**: Nothing
  - **Effort**: Small
  - **Verification**: `test -f ARCHITECTURE.md && ! test -f PROJECT_README.md`

- [ ] **T08** Create `CONTRIBUTING.md`
  - **File**: `CONTRIBUTING.md` (new file at repo root)
  - **Action**: Create a contributing guide for public audience. Include sections:
    - How to report bugs (open an issue)
    - How to suggest features (open an issue with label)
    - Development setup (reference README.md Quick Start)
    - Code style (Python: ruff/black, TypeScript: ESLint/Prettier — or whatever the project uses)
    - Pull request process (fork, branch, commit, PR)
    - License (GPL v3 — reference LICENSE file)
  - **Depends on**: Nothing (but logically follows T05 since it references the license)
  - **Effort**: Medium
  - **Verification**: `test -f CONTRIBUTING.md && grep -q 'GPL' CONTRIBUTING.md`

- [ ] **T09** Create root `.dockerignore`
  - **File**: `.dockerignore` (new file at repo root)
  - **Action**: Create with these exclusions:
    ```
    .git/
    .venv/
    __pycache__/
    *.py[cod]
    frontend/.next/
    frontend/node_modules/
    frontend/out/
    tests/
    openspec/
    .github/
    .vscode/
    .idea/
    *.md
    !README.md
    .env
    .DS_Store
    .atl/
    ```
  - **Detail**: Keeps Docker build context small. The `!README.md` exception ensures the README is available if needed by the build. `*.md` excludes ARCHITECTURE.md, CONTRIBUTING.md, etc. from context.
  - **Depends on**: Nothing
  - **Effort**: Small
  - **Verification**: `test -f .dockerignore && grep -q 'frontend/.next/' .dockerignore`

- [ ] **T10** Add dev-password comment to `docker-compose.yml`
  - **File**: `docker-compose.yml`
  - **Action**: Add a comment above the `POSTGRES_PASSWORD: rag` line (line 6) warning that this is a dev-only password.
  - **Detail**: Change line 6 from:
    ```yaml
          POSTGRES_PASSWORD: rag
    ```
    to:
    ```yaml
          POSTGRES_PASSWORD: rag  # Dev only — change in production
    ```
    Also add a similar inline comment on `POSTGRES_USER: rag` (line 5) for consistency.
  - **Depends on**: Nothing
  - **Effort**: Small
  - **Verification**: `grep -q 'Dev only' docker-compose.yml`

- [ ] **T11** Create `frontend/app/icon.svg` favicon
  - **File**: `frontend/app/icon.svg` (new file)
  - **Action**: Create a minimal SVG favicon. Next.js App Router convention: place `icon.svg` in `app/` directory and it's automatically served as the site favicon.
  - **Detail**: Use a simple, clean SVG — e.g., a rounded rectangle with "AI" text or a simple geometric shape. Keep it under 1 KB. Example:
    ```svg
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
      <rect width="32" height="32" rx="6" fill="#2563eb"/>
      <text x="16" y="22" font-family="system-ui" font-size="16" font-weight="bold" fill="white" text-anchor="middle">AI</text>
    </svg>
    ```
  - **Depends on**: Nothing
  - **Effort**: Small
  - **Verification**: `test -f frontend/app/icon.svg && head -1 frontend/app/icon.svg | grep -q '<svg'`

## Phase 3: Commit + Squash (Sequential)

Create a clean single-commit history via orphan branch.

- [ ] **T12** Create orphan branch and squash all changes into a single clean commit
  - **Commands**:
    ```bash
    # Stage all changes from Phases 1-2
    git add -A

    # Create orphan branch (no history)
    git checkout --orphan clean-main

    # Stage everything on the orphan branch
    git add -A

    # Commit with a descriptive message
    git commit -m "feat: initial public release

    - FastAPI backend with hexagonal architecture
    - Next.js frontend with RAG chat interface
    - pgvector + Ollama for local LLM inference
    - Docker Compose for local development
    - GPL v3 license
    - Sample documents for testing"

    # Replace main with the orphan branch
    git branch -M clean-main main

    # Force-update the ref (local only, no push yet)
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    ```
  - **Detail**: This eliminates all 1823 build artifacts from git history. The resulting `.git` directory should be under 5 MB. The `git gc --prune=now --aggressive` ensures old objects are purged.
  - **Depends on**: T01-T11 all complete and staged
  - **Effort**: Medium
  - **Verification**: `git log --oneline | wc -l` returns 1; `du -sh .git/` is under 10 MB

## Phase 4: Verification (Sequential)

Final checks before the repo is ready for `git push`.

- [ ] **T13** Verify no build artifacts are tracked in git
  - **Command**: `git ls-files --cached | grep -E '(frontend/\.next/|__pycache__|\.atl/)' | wc -l`
  - **Expected**: Returns `0`
  - **Depends on**: T12 (post-squash verification)
  - **Effort**: Small

- [ ] **T14** Verify no broken README references remain
  - **Command**: `grep -n 'sample_contract\|technical_spec\|LangChain' README.md`
  - **Expected**: No output (exit code 1)
  - **Depends on**: T12
  - **Effort**: Small

- [ ] **T15** Verify all new files exist
  - **Command**:
    ```bash
    for f in LICENSE ARCHITECTURE.md CONTRIBUTING.md .dockerignore frontend/app/icon.svg; do
      test -f "$f" && echo "OK: $f" || echo "MISSING: $f"
    done
    ```
  - **Expected**: All files report `OK`
  - **Also verify**: `PROJECT_README.md` does NOT exist; `docker-compose.yml` contains dev-password comment
  - **Depends on**: T12
  - **Effort**: Small

- [ ] **T16** Docker Compose configuration smoke test
  - **Command**: `docker compose config > /dev/null`
  - **Expected**: Exit code 0 (valid YAML, all references resolve)
  - **Detail**: This validates that docker-compose.yml is still valid after the comment addition and that the .dockerignore doesn't break anything. Full `docker compose build` is optional and may be skipped if Docker is not available or build times are prohibitive.
  - **Depends on**: T12
  - **Effort**: Small
  - **Verification**: Exit code 0
