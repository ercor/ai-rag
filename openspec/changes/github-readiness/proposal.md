# Proposal: GitHub Readiness for ai-rag

## Intent

Make the ai-rag repository safe, professional, and presentable for public GitHub upload by removing 1,800+ tracked build artifacts, adding legal licensing, fixing broken documentation references, and establishing a clean project structure — reducing repo size from 120 MB to under 5 MB.

## Scope

### In Scope

1. **Git repository cleanup** — Remove 1,786 `frontend/.next/` build artifacts, 35 `__pycache__/*.pyc` files, and `.atl/` tool metadata from git tracking. Add `.atl/` to `.gitignore`.
2. **Legal foundation** — Add a LICENSE file (MIT recommended).
3. **README corrections** — Fix references to non-existent sample documents (lines 369-370), remove unnecessary LangChain mention (line 863).
4. **Documentation structure** — Rename `PROJECT_README.md` → `ARCHITECTURE.md` to eliminate dual-README confusion. Add `CONTRIBUTING.md` for public audience.
5. **Docker build hygiene** — Create root `.dockerignore` to exclude `.git`, `.venv`, `__pycache__`, `.next`, `node_modules`, `tests`, `openspec` from Docker context. Add dev-only comment to `docker-compose.yml` password.
6. **Frontend polish** — Add a favicon to `frontend/public/`.
7. **openspec/ decision** — Keep `openspec/` tracked as documentation of the development methodology (recommended) or remove it. Decision needed before apply.

### Out of Scope

- **CI/CD pipeline setup** — No `.github/workflows/` creation. CI badges are deferred until CI exists.
- **Screenshots/demo GIF** — Requires running the application and capturing media. Deferred to a follow-up.
- **Git history rewrite** — `git filter-branch` or BFG Repo-Cleaner to purge artifacts from history is NOT in scope. The initial public push should use a fresh history (squash or single commit) or accept that history contains artifacts until first rewrite.
- **CODE_OF_CONDUCT.md, CHANGELOG.md** — Nice to have but not blocking for initial upload.
- **Code changes** — No source code modifications. The codebase is clean.

## Capabilities

> This is a housekeeping and documentation change. No spec-level behavior is affected.

### New Capabilities

None

### Modified Capabilities

None

## Approach

The work is grouped into five sequential work units, ordered by priority:

### Work Unit 1: Git Cleanup (CRITICAL — do first)

Remove build artifacts and tool metadata from git tracking:

```bash
git rm -r --cached frontend/.next/
git rm -r --cached '**/__pycache__'
git rm -r --cached .atl/
```

Add `.atl/` to `.gitignore` if not already present. Commit as a single cleanup commit.

**Decision gate**: `openspec/` — keep or remove? Recommendation: **keep** as methodology documentation. If keeping, no action needed. If removing, add to this work unit.

### Work Unit 2: Legal & Licensing (CRITICAL)

Add `LICENSE` file at repository root. MIT License recommended for open-source educational projects. Update README to reference the license.

### Work Unit 3: README & Documentation (CRITICAL + WARNING)

- Fix `README.md` lines 369-370: replace `sample_contract.txt` → `travel_policy.md`, `technical_spec.md` → `q3_results.md` (or `engineering_onboarding.md`).
- Remove line 863 LangChain mention.
- Rename `PROJECT_README.md` → `ARCHITECTURE.md`.
- Create `CONTRIBUTING.md` with: development setup, how to run tests, code style (ruff), PR guidelines.

### Work Unit 4: Docker & Build Configuration (WARNING)

- Create root `.dockerignore` excluding: `.git`, `.venv`, `__pycache__`, `.next`, `node_modules`, `tests`, `openspec`, `.atl`, `*.md` (except README).
- Add comment to `docker-compose.yml` above the `POSTGRES_PASSWORD: rag` line: `# Dev-only default. Change for production use.`

### Work Unit 5: Frontend Polish (INFO)

- Add a minimal `favicon.ico` to `frontend/public/`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/.next/` | Removed from git | 1,786 build artifact files untracked |
| `src/**/__pycache__/`, `tests/**/__pycache__/` | Removed from git | 35 .pyc files untracked |
| `.atl/` | Removed from git + .gitignore | 2 tool metadata files untracked |
| `LICENSE` | New file | MIT License at repository root |
| `README.md` | Modified | Fix sample doc refs (L369-370), remove LangChain mention (L863) |
| `PROJECT_README.md` → `ARCHITECTURE.md` | Renamed | Clarify purpose as internal architecture doc |
| `CONTRIBUTING.md` | New file | Public contributing guide |
| `.dockerignore` | New file | Root-level Docker build context exclusions |
| `docker-compose.yml` | Modified | Add dev-only comment to password line |
| `frontend/public/favicon.ico` | New file | Minimal favicon |
| `.gitignore` | Modified | Add `.atl/` entry if missing |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Git history still contains 80 MB of build artifacts even after `git rm --cached` | High | For initial public push, create a fresh repo with squashed history OR accept bloated history and rewrite later with BFG. Document the tradeoff. |
| `openspec/` contains internal SDD workflow artifacts that may not be appropriate for public view | Low | Review `openspec/` contents before deciding. Archived changes contain design docs and specs — these demonstrate professional methodology. Recommendation: keep. |
| MIT License may not match author's intent (README says "as-is for educational") | Low | MIT is compatible with "as-is for educational". Confirm with author before committing. |
| Renaming `PROJECT_README.md` → `ARCHITECTURE.md` may break internal links or references | Low | Search for references to `PROJECT_README.md` before renaming. Update any links found. |
| `frontend/public/favicon.ico` requires a binary file — cannot be generated as text | Low | Use a minimal 1x1 pixel favicon or a simple text-based SVG favicon. Alternatively, skip and add a placeholder comment. |

## Rollback Plan

All changes are reversible:

1. **Git cleanup**: `git revert <cleanup-commit>` restores tracked artifacts. No data loss — files remain on disk.
2. **LICENSE**: Delete the file. No side effects.
3. **README fixes**: `git revert <readme-commit>` or manual edit.
4. **Rename PROJECT_README.md**: `git mv ARCHITECTURE.md PROJECT_README.md`.
5. **New files** (CONTRIBUTING.md, .dockerignore, favicon.ico): Delete them.
6. **docker-compose.yml comment**: `git revert <docker-commit>` or remove comment.

If multiple commits were made, a single `git revert --no-commit <range>` followed by one commit can undo everything atomically.

## Dependencies

- **License choice**: Author must confirm MIT vs Apache 2.0 vs other. Default assumption: MIT.
- **openspec/ decision**: Author must confirm keep vs remove. Default assumption: keep.
- **No external dependencies**: All changes are local file operations. No new packages, no infrastructure.

## Success Criteria

- [ ] `git ls-files | grep -c '.next/'` returns 0 (no build artifacts tracked)
- [ ] `git ls-files | grep -c '__pycache__'` returns 0 (no cache files tracked)
- [ ] `git ls-files | grep -c '.atl/'` returns 0 (no tool metadata tracked)
- [ ] `LICENSE` file exists at repository root
- [ ] `README.md` contains no references to `sample_contract.txt` or `technical_spec.md`
- [ ] `README.md` contains no mention of LangChain
- [ ] `ARCHITECTURE.md` exists (renamed from `PROJECT_README.md`)
- [ ] `CONTRIBUTING.md` exists with development setup instructions
- [ ] `.dockerignore` exists at repository root with standard exclusions
- [ ] `docker-compose.yml` has a comment above the dev password
- [ ] `frontend/public/favicon.ico` exists (or documented decision to skip)
- [ ] `openspec/` decision documented (keep or remove)
- [ ] Repository size under 10 MB (ideal: under 5 MB after cleanup + gc)
- [ ] No secrets, tokens, or private URLs in any tracked file (re-verify after changes)
- [ ] Project can be cloned and `docker compose up` works from a clean checkout

## Open Decisions

These require author input before the apply phase:

1. **License**: MIT (recommended) or Apache 2.0?
2. **openspec/**: Keep as methodology documentation (recommended) or remove from tracking?
3. **Git history**: Fresh squash for initial push (recommended) or accept bloated history?
4. **Favicon**: Generate a minimal one, use a placeholder, or skip?
