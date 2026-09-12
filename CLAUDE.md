# CLAUDE.md — job-market-pipeline

Public job-posting ELT pipeline: `pull_jobs.py` extracts Greenhouse/Lever boards into SQLite → **dbt (DuckDB) transforms** → Streamlit + Tableau. The dbt layer is the current work and the reason this project is on the resume.

## Source of truth

Read these before doing anything, every session:

- `docs/plan/00_DBT_BRIEF.md` — vision, reviewer rubric, scope, target layout
- `docs/plan/01_DBT_ROADMAP.md` — phased checkboxes with exit tests. **Work one checkbox per session.**
- `docs/plan/02_DBT_DECISIONS.md` — ADRs and open questions. Follow them; supersede with a new ADR rather than drifting.

## Session protocol

1. Nick names the roadmap checkbox. If he doesn't, ask which one before writing code.
2. Do that checkbox only. A new idea mid-session goes in the roadmap's Phase D list, not into code.
3. Before finishing: run the checkbox's exit test, tick the box in `01_DBT_ROADMAP.md`, append an ADR if a decision was made, resolve any OQ that got answered.
4. Commit per checkbox with a descriptive message. Never one giant commit.

## Ownership split — this matters

The purpose of the project is that Nick can explain every model in an interview. So:

**Claude Code writes these (boilerplate, not the story):**
- B0: `pull_jobs.py` changes (`first_seen_at` / `last_seen_at`)
- B1: `dbt/` scaffold, `dbt_project.yml`, `profiles.yml`, `packages.yml`, `.gitignore`
- B6: docs build + GitHub Pages workflow, `exposures.yml` plumbing
- B7: `.github/workflows/dbt.yml`, sqlfluff config, pre-commit, sample DB script
- B8: `app.py` / `export_for_tableau.py` rewiring, README diagram and badges

**Nick writes these; Claude Code reviews only, unless explicitly asked to draft:**
- B2: `stg_*` models and their YAML
- B3: `snapshots/*.yml`
- B4: `macros/*.sql`, `int_*` models, unit tests
- B5: `dim_*` / `fct_*` models, contracts, singular tests

"Review" means: check against the dbt Labs structure guide and SQL style guide, point at the exact lines to change, and explain why. Do not silently rewrite the file. If Nick asks "just write it," draft it, then ask him to explain it back before it is committed.

## Environment

- CachyOS, fish shell. Activate with `source .venv/bin/activate.fish` (not `activate`).
- Python managed with uv. `uv sync` at repo root.
- dbt commands run from `dbt/`: `dbt debug`, `dbt build`, `dbt snapshot`, `dbt docs generate`.
- Pin `dbt-core>=1.12,<2` and `dbt-duckdb`. No dbt Core 2.0 until Phase B ships (ADR-001).
- Daily workflow once B3 ships: `python pull_jobs.py` → `cd dbt && dbt snapshot && dbt build` → `python export_for_tableau.py`.

## Conventions (details in the decisions log)

- dbt Labs project structure and naming exactly: `staging/` views → `intermediate/` views → `marts/` tables (ADR-004).
- Raw SQLite is attached read-only inside DuckDB via `profiles.yml`; never write to it from dbt (ADR-003).
- History: snapshot with check strategy on content columns + `last_seen_at` for closure (ADR-005).
- Every model has a description; every primary key has `unique` + `not_null`.
- Public data only. No credentials anywhere. `*.duckdb`, `target/`, `dbt_packages/`, `logs/` are gitignored.

## Never

- Skip ahead on the roadmap or add models that aren't on it
- Write a file in the "Nick writes" list without being asked
- Touch `pull_jobs.py` outside the B0 scope
- Add incremental models, a semantic layer, new API sources, or a dbt platform account
- Commit a `.duckdb` file
