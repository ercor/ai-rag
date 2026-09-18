# Design: GitHub Readiness for ai-rag

## Technical Approach

Prepare the ai-rag repository for public GitHub upload through six coordinated work units: git artifact cleanup, GPL v3 licensing, README corrections, documentation restructure, Docker hygiene, and frontend favicon. The changes are purely structural — no source code modifications. The execution order is designed so that the git squash (which rewrites history) happens last, producing a single clean initial commit with all improvements included.

Reference: proposal `sdd/github-readiness/proposal` (observation #461).

## Architecture Decisions

### Decision: Git artifact removal strategy

**Choice**: `git rm -r --cached` to untrack artifacts, then `git checkout --orphan` for a fresh squash before initial push.

**Alternatives considered**:
- `git filter-branch` / BFG Repo-Cleaner — overkill for a pre-push repo; adds tool dependency
- `git rebase -i --root` — interactive, fragile with 1800+ file changes, harder to verify
- Accept bloated history — leaves 120 MB `.git/` in every clone

**Rationale**: `git rm --cached` is the standard, reversible way to untrack files while keeping `.gitignore` enforcement. The orphan-branch squash produces a single-commit history that is trivially clean for a first public push. No external tools needed. The `.git` directory drops from 120 MB to under 5 MB.

### Decision: GPL v3 license

**Choice**: Full GPL v3 text in `LICENSE` file, with copyright line: `Copyright (C) 2026 The ai-rag authors`.

**Alternatives considered**:
- MIT / Apache 2.0 — proposal recommended MIT, but user explicitly chose GPL v3
- SPDX short identifier only — insufficient for GPL v3 compliance; full text required

**Rationale**: User decision. GPL v3 requires the full license text. "The ai-rag authors" is a neutral holder that avoids pinning to a personal name. The year 2026 matches the project's creation date.

### Decision: README sample document references

**Choice**: Replace `sample_contract.txt` → `travel_policy.md` and `technical_spec.md` → `q3_results.md` in ALL locations (lines 369-370, 483, 497-498). Update citation examples to match actual document content.

**Alternatives considered**:
- Remove sample doc section entirely — loses useful onboarding context
- Use `engineering_onboarding.md` instead — less intuitive as a "sample" for new users

**Rationale**: The `data/docs/` directory contains exactly three files: `travel_policy.md`, `q3_results.md`, `engineering_onboarding.md`. The README references must match reality. `travel_policy.md` maps naturally to the "contract" example (policy document), and `q3_results.md` maps to the "technical spec" example (structured report). Citation examples at lines 483 and 497-498 must also be updated to reference the correct filenames and plausible section names from those documents.

### Decision: LangChain mention removal

**Choice**: Remove line 863 entirely (`- **LangChain** - Inspiration for RAG patterns (not used in implementation)`).

**Alternatives considered**:
- Keep with clarification — adds confusion; public readers will assume LangChain is a dependency
- Replace with actual tools used — the acknowledgments already list the real stack

**Rationale**: The project does not use LangChain. Mentioning it in a public README invites false assumptions about dependencies and may attract incorrect issue reports. The remaining acknowledgments (Ollama, pgvector, FastAPI, Next.js) accurately reflect the stack.

### Decision: PROJECT_README.md → ARCHITECTURE.md rename

**Choice**: `git mv PROJECT_README.md ARCHITECTURE.md`. Do NOT update references inside `openspec/` historical documents.

**Alternatives considered**:
- Move to `docs/ARCHITECTURE.md` — adds a directory level for no benefit; the root is fine for a single architecture doc
- Update openspec/ references — those are historical methodology artifacts; modifying them rewrites history unnecessarily

**Rationale**: The rename eliminates dual-README confusion. References to `PROJECT_README.md` exist only in `openspec/changes/` exploration and proposal documents, which are SDD methodology artifacts — they document the process that led to this rename and should remain as-is for historical accuracy.

### Decision: CONTRIBUTING.md structure

**Choice**: Create `CONTRIBUTING.md` at repo root with four sections: Development Setup, Testing, Code Style, Pull Request Process.

**Alternatives considered**:
- GitHub default template — too generic, doesn't reflect this project's hexagonal architecture
- Full contributor covenant + guide — overkill for initial upload; add later if community grows

**Rationale**: A public repo needs a minimal CONTRIBUTING.md to signal openness and set expectations. The four sections cover what a new contributor needs to get started without being prescriptive about things that don't exist yet (like CI badges or branch naming conventions).

### Decision: Root .dockerignore

**Choice**: Create root `.dockerignore` excluding: `.git`, `.venv`, `__pycache__`, `.next`, `node_modules`, `tests`, `openspec`, `.env`, `.env.example`, `*.md`, `.pytest_cache`, `.ruff_cache`, `.atl`, `data/docs/*.pdf`, `data/docs/*.docx`.

**Alternatives considered**:
- Minimal ignore (just `.git`, `node_modules`) — leaves large unnecessary files in Docker context
- Mirror frontend/.dockerignore exactly — different context; root builds the backend, not the frontend

**Rationale**: The root Dockerfile (`Dockerfile.backend`) builds only the Python backend. Excluding test files, docs, caches, and VCS data reduces build context from ~644 MB to under 50 MB, speeding up `docker compose build` significantly. The frontend has its own `.dockerignore` already.

### Decision: docker-compose.yml dev password comment

**Choice**: Add inline comment `# DEV ONLY - change in production` on the `POSTGRES_PASSWORD: rag` line and the `DATABASE_URL` connection string.

**Alternatives considered**:
- Move password to `.env` file — good practice but changes the setup flow; defer to a follow-up
- Add a prominent warning block at top of file — too noisy for a single-line concern

**Rationale**: Inline comments are the minimum viable warning. They travel with the file and are visible at the exact point of concern. Moving to `.env` is a larger change that affects the quick-start flow.

### Decision: Favicon approach

**Choice**: Create a minimal inline SVG favicon at `frontend/public/favicon.svg` and reference it from the Next.js app layout. The SVG is a simple geometric shape (e.g., a document icon or "AI" monogram) encoded directly.

**Alternatives considered**:
- `favicon.ico` binary — requires external tool or base64-encoded blob in git
- Skip favicon — browsers show broken icon; looks unprofessional
- Generate with a build tool — adds dependency for a one-time artifact

**Rationale**: An SVG favicon is text-based (diff-friendly), tiny (< 500 bytes), requires no build step, and Next.js supports it natively via `app/favicon.ts` or by placing `favicon.ico`/`favicon.svg` in `public/`. A simple SVG keeps the repo clean. Next.js App Router auto-detects `app/favicon.ico` — placing a minimal `.ico` generated from the SVG is the most compatible approach. We'll create a minimal SVG and convert to a tiny `.ico` inline (or just use the SVG directly since modern browsers support it).

**Refined choice**: Create `frontend/public/favicon.ico` as a minimal valid ICO file (a 16x16 or 32x32 single-color icon encoded as base64 in a small script, or hand-crafted binary). Simplest approach: use a Python one-liner during apply to generate a minimal valid `.ico` from raw bytes. Alternatively, place an `icon.svg` in `frontend/app/` which Next.js App Router handles natively.

**Final choice**: Create `frontend/app/icon.svg` — Next.js App Router automatically generates favicon metadata from this. The SVG is a simple "AI" text or document icon. This is the idiomatic Next.js 14+ approach and avoids binary files in git.

## Data Flow

No data flow changes. This is a structural/metadata change with no runtime impact:

```
Before:                          After:
┌─────────────────────┐          ┌─────────────────────┐
│ .next/ (1786 files) │──tracked─│ .gitignore enforces │
│ __pycache__/ (35)   │──tracked─│ untracked, clean    │
│ .atl/ (2)           │──tracked─│                     │
│ LICENSE (missing)   │          │ LICENSE (GPL v3)    │
│ README.md (broken)  │          │ README.md (fixed)   │
│ PROJECT_README.md   │          │ ARCHITECTURE.md     │
│ .dockerignore (no)  │          │ .dockerignore (yes) │
│ favicon (missing)   │          │ app/icon.svg        │
└─────────────────────┘          └─────────────────────┘
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `.gitignore` | Modify | Add `.atl/` entry |
| `LICENSE` | Create | GPL v3 full text with copyright line |
| `README.md` | Modify | Fix sample doc refs (L369-370, L483, L497-498), remove LangChain mention (L863) |
| `PROJECT_README.md` → `ARCHITECTURE.md` | Rename | Clarify purpose as architecture doc |
| `CONTRIBUTING.md` | Create | Dev setup, testing, code style, PR process |
| `.dockerignore` | Create | Root-level Docker build context exclusions |
| `docker-compose.yml` | Modify | Add dev-password comments on lines 6 and 38 |
| `frontend/app/icon.svg` | Create | Minimal SVG icon for Next.js App Router favicon |

**Git operations** (not file changes but part of execution):
- `git rm -r --cached frontend/.next/` — untrack 1786 build artifacts
- `git rm -r --cached '**/__pycache__'` — untrack 35 .pyc files
- `git rm -r --cached .atl/` — untrack 2 tool metadata files
- `git checkout --orphan main` + squash — fresh single-commit history

## Interfaces / Contracts

No new interfaces. The changes are file-level only.

### .gitignore addition

```gitignore
# Tool metadata
.atl/
```

### Root .dockerignore

```dockerignore
# VCS and tooling
.git
.atl
.vscode
.idea

# Python
.venv
__pycache__
*.py[cod]
.pytest_cache
.ruff_cache
*.egg-info

# Node / Frontend build
frontend/node_modules
frontend/.next
frontend/out

# Tests and docs
tests
openspec
data/docs/*.pdf
data/docs/*.docx

# Environment
.env
.env.example

# Misc
.DS_Store
*.md
```

### docker-compose.yml comment additions

```yaml
# Line 6 (inside postgres service):
      POSTGRES_PASSWORD: rag  # DEV ONLY - change in production

# Line 38 (inside backend service):
      DATABASE_URL: postgresql+asyncpg://rag:rag@postgres:5432/rag  # DEV ONLY - change password in production
```

### README.md citation example updates

Lines 369-370 become:
```markdown
- `data/docs/travel_policy.md` - Example travel policy
- `data/docs/q3_results.md` - Example quarterly results report
```

Line 483 becomes:
```markdown
- [1] travel_policy.md → Section 4: Payment Terms
```
(Adjust section name to match actual content of travel_policy.md during apply.)

Lines 497-498 become:
```markdown
- [1] q3_results.md → Section 2: Performance Requirements
- [2] q3_results.md → Section 3: Reliability Requirements
```
(Adjust section names to match actual content of q3_results.md during apply.)

Line 863 — delete entirely:
```markdown
- **LangChain** - Inspiration for RAG patterns (not used in implementation)
```

### frontend/app/icon.svg

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="4" fill="#1a1a2e"/>
  <text x="16" y="22" font-family="system-ui, sans-serif" font-size="14" font-weight="bold" fill="#e0e0e0" text-anchor="middle">AI</text>
</svg>
```

Minimal, text-based, diff-friendly, < 300 bytes.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Verification | No build artifacts tracked | `git ls-files | grep -E '\.next\|__pycache__\|\.atl'` returns empty |
| Verification | LICENSE file valid | `head -1 LICENSE` shows GPL v3 header |
| Verification | README has no broken refs | `grep -E 'sample_contract\|technical_spec\|LangChain' README.md` returns empty |
| Verification | ARCHITECTURE.md exists | `test -f ARCHITECTURE.md` |
| Verification | .dockerignore exists | `test -f .dockerignore` |
| Verification | Favicon present | `test -f frontend/app/icon.svg` |
| Smoke | Docker build works | `docker compose build` succeeds from clean checkout |
| Smoke | App starts | `docker compose up` serves frontend on :3000 and backend on :8000 |

No unit/integration/E2E tests needed — no source code changes.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The git commands are one-time cleanup operations, not runtime shell integration.

## Migration / Rollout

### Execution Order

The tasks are ordered to minimize conflicts and ensure the final squash captures everything:

```
Phase 1: Git cleanup (untrack artifacts)
  ├── 1a. Add .atl/ to .gitignore
  ├── 1b. git rm -r --cached frontend/.next/
  ├── 1c. git rm -r --cached '**/__pycache__'
  └── 1d. git rm -r --cached .atl/

Phase 2: File changes (can be parallel)
  ├── 2a. Create LICENSE (GPL v3)
  ├── 2b. Fix README.md (sample docs, LangChain, citation examples)
  ├── 2c. git mv PROJECT_README.md ARCHITECTURE.md
  ├── 2d. Create CONTRIBUTING.md
  ├── 2e. Create .dockerignore
  ├── 2f. Modify docker-compose.yml (dev password comments)
  └── 2g. Create frontend/app/icon.svg

Phase 3: Commit and squash
  ├── 3a. git add -A
  ├── 3b. git commit -m "chore: prepare repository for public GitHub upload"
  └── 3c. git checkout --orphan main (squash to single commit)

Phase 4: Verification
  ├── 4a. Confirm no artifacts tracked
  ├── 4b. Confirm all new files present
  └── 4c. docker compose build smoke test
```

**Parallelism**: Phase 2 tasks (2a-2g) are fully independent and can execute in parallel. Phase 1 must complete before Phase 3. Phase 3 must complete before Phase 4.

### Rollout Notes

- The orphan-branch squash destroys existing git history. This is intentional (per decisions) but means any existing branches or PRs are invalidated.
- After squash, the remote must be set up fresh: `git remote add origin <url> && git push -u origin main`.
- If the repo already has a remote with history, force-push is required: `git push --force origin main`.

## Open Questions

- [ ] **Copyright holder name**: "The ai-rag authors" is proposed. Should it be a personal name instead? (Non-blocking — can use placeholder and update later.)
- [ ] **Citation example section names**: The README citation examples reference specific sections (e.g., "Section 4: Payment Terms"). During apply, verify these section names match the actual content of `travel_policy.md` and `q3_results.md`, adjusting if needed.
