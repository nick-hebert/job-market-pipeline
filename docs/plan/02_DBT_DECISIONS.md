# dbt Portfolio Project — Decision Log

> Append-only. Never edit an accepted decision — supersede it with a new one. Format: context → decision → consequences. Decisions 001–006 were made at planning time (2026-09-12) with zero lines of code; they are the cheapest possible moment to be wrong, so revisit freely by superseding.

---

## ADR-001: dbt Core + dbt-duckdb, no platform, no warehouse
**Status:** Accepted · **Date:** 2026-09-12

**Context:** dbt can run against any warehouse or via dbt's hosted platform. Reviewers check for dbt *skills* (structure, tests, docs, snapshots), not for which backend ran it. A warehouse account adds credentials, cost, and a setup step that breaks "clone and run."

**Decision:** dbt Core **1.12.x** with the **dbt-duckdb** adapter. Build target is a local DuckDB file (`dbt/job_market.duckdb`, gitignored). No dbt platform account. Pin `dbt-core>=1.12,<2` until ADR supersedes.

**Consequences:** Zero infrastructure; reviewer reproduces in minutes; same stack as DAT so knowledge transfers. dbt Core 2.0 (Rust engine, release-candidate as of Sept 2026) is a deliberate later upgrade, not a starting point — project structure and YAML are identical, so nothing learned is wasted.

---

## ADR-002: The dbt project lives inside `job-market-pipeline` at `dbt/`
**Status:** Accepted · **Date:** 2026-09-12

**Context:** Could be a standalone repo (`job-market-dbt`) or a directory in the existing pipeline repo. Standalone is more discoverable by name; in-repo tells the whole ELT story at one link and reuses the existing README, screenshot, and commit history.

**Decision:** Directory `dbt/` inside `job-market-pipeline`, dbt project name `job_market`. The repo README becomes the architecture narrative (extract → load → transform → visualize). Repo description and topics updated to include `dbt`.

**Consequences:** One portfolio link shows the full pipeline; the repo's existing history counts. Cost: reviewers searching GitHub for "dbt" repos won't find it by name — mitigated by README title, topics, and the resume bullet linking directly.

---

## ADR-003: Raw SQLite attached read-only via dbt-duckdb `attach`; loader untouched
**Status:** Accepted · **Date:** 2026-09-12

**Context:** `pull_jobs.py` writes SQLite. Options: (a) rewrite the loader to write DuckDB, (b) export SQLite → Parquet as a pre-step, (c) attach the SQLite file directly inside DuckDB using its sqlite extension, which dbt-duckdb supports natively in `profiles.yml`.

**Decision:** Option (c). `profiles.yml` (committed — local paths only, no secrets):

```yaml
job_market:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: job_market.duckdb
      threads: 4
      extensions:
        - sqlite
      attach:
        - path: ../jobs.db          # raw SQLite from pull_jobs.py — filename confirmed in B0
          type: sqlite
          alias: raw
          read_only: true
    ci:
      type: duckdb
      path: ":memory:"
      extensions:
        - sqlite
      attach:
        - path: sample/jobs_sample.db
          type: sqlite
          alias: raw
          read_only: true
```

Sources are declared with `database: raw`. Staging models cast types explicitly because SQLite's loose typing arrives loosely.

**Consequences:** Zero loader rewrite; a clean raw/transformed boundary (raw is read-only by construction); demonstrates a real-world pattern (dbt over an existing system you don't own). Risk: if the attach proves flaky, supersede with option (b) — a five-line Parquet export — without touching the models.

---

## ADR-004: Layering and naming follow dbt Labs conventions exactly
**Status:** Accepted · **Date:** 2026-09-12

**Context:** Reviewers pattern-match against the dbt Labs "How we structure our dbt projects" guide. Deviation reads as not knowing the convention, not as creativity.

**Decision:**
- `staging/<source>/` — one model per source table, 1:1, rename + cast + trim only, materialized as **views**. Named `stg_<source>__<entity>`.
- `intermediate/` — business logic that isn't yet a final table, materialized as **views** (ephemeral only if a model is referenced by exactly one parent). Named `int_<entity>__<verb>`.
- `marts/` — `fct_` and `dim_` tables, materialized as **tables**, with enforced contracts.
- YAML files prefixed with `_` and named per folder (`_job_boards__sources.yml`, `_marts__models.yml`).
- Every model has a description; every primary key has `unique` + `not_null`.
- No incremental models in v1 — the data is ~2.4k rows; say so in the README rather than cargo-cult it.

**Consequences:** Boring, recognizable, defensible in interview. The materialization choices are explainable in one sentence each.

---

## ADR-005: History = dbt snapshot on content + `last_seen_at` for closure
**Status:** Accepted · **Date:** 2026-09-12

**Context:** The raw table is upserted; it never deletes and (probably) never records when a posting stopped appearing. Two distinct history questions: *what changed on a posting* (title, location) and *when did it close*. A snapshot alone can't see closure because the raw row never disappears.

**Decision:**
- **Content changes:** dbt snapshot (YAML-defined, dbt ≥1.9 style) over the source with **check strategy** on `[title, location, department, workplace_type]`. Runs daily after the pull.
- **Closure:** `pull_jobs.py` maintains `first_seen_at` (set on insert) and `last_seen_at` (bumped every run the posting appears). `int_postings__lifecycle` derives `is_active = last_seen_at = max(last_seen_at)` and `closed_at = last_seen_at where not is_active`. No snapshot needed for this.
- **Not chosen (yet):** timestamp strategy on an API `updated_at` — see OQ-2; `hard_deletes: new_record` over a staging view filtered to active postings — elegant, but it's the stretch version, not v1.

**Consequences:** Two small mechanisms instead of one clever one; each explainable in a sentence. History starts accumulating the day B3 ships — earlier is better, which is why B0/B3 are front-loaded. Interview line: "the pipeline was losing history every day; snapshots plus a last-seen column turned a flat list into a time series."

---

## ADR-006: CI runs `dbt build` against a committed sample SQLite
**Status:** Accepted · **Date:** 2026-09-12

**Context:** CI needs raw data. Options: call the job-board APIs in CI (flaky, slow, rate-limited), seeds (means maintaining CSV copies of the raw table), or a committed sample SQLite. The data is public job postings — no scrub step required.

**Decision:** `dbt/sample/jobs_sample.db` — a ~200-row cut of the real raw table, refreshed manually when the schema changes. CI target (`ci` in ADR-003) attaches it. `dbt build --target ci` on every PR; docs deploy to GitHub Pages on merge to main from the same workflow.

**Consequences:** CI is fast and deterministic; the sample doubles as the "try it without running the extractor" path in the README. Cost: the sample can drift from the real schema — mitigated by a checklist item in B0 whenever `pull_jobs.py` changes the table.

---

## Open Questions (resolve as ADRs or inline; strike through when done)

- **OQ-1: One staging model or one per source?** Depends on the raw schema. If `pull_jobs.py` already normalizes Greenhouse and Lever into one column set (likely — it upserts on `(source, source_job_id)`), one `stg_job_boards__postings` with a `source` column is correct and honest. If source-specific columns survive in the raw table, split into `staging/greenhouse/` and `staging/lever/` and union in `int_postings__unioned`. **Resolve in B0 from `.schema jobs`.**
- **OQ-2: Snapshot strategy — check vs timestamp.** Greenhouse exposes `updated_at`; whether Lever's `updatedAt` is stored depends on the loader. If both sources have a reliable per-posting updated timestamp in the raw table, `timestamp` strategy is cheaper and idiomatic; otherwise `check` (ADR-005 default). **Resolve in B0.**
- **OQ-3: Sample DB size and refresh rule.** ~200 rows across all 15 companies, regenerated by a small script (`scripts/make_sample.py`) so it's reproducible. **Confirm in B7.**
- **OQ-4: Docs hosting shape.** `dbt docs generate --static` yields one self-contained `index.html` (fits the self-contained-HTML ethos from DAT). Publish to `gh-pages` via Actions, or commit under `docs/dbt/` and point Pages at it. **Decide in B6 — lean Actions → gh-pages.**
- **OQ-5: Workplace-type classification source.** Lever postings carry a workplace-type field; Greenhouse doesn't — it's inferred from `location.name` and the title ("Remote", "Hybrid", "US-Remote"). Macro takes the explicit field when present, regex otherwise, and records which path was used in a `workplace_type_source` column so the inference is auditable. **Confirm field availability in B0; build in B4.**
- **OQ-6: Seniority bucketing rules.** Title regex (intern / junior / mid / senior / staff / lead / manager / director) is crude but honest if documented as such. Decide whether it belongs in v1 or Phase D. **Decide in B4.**
- **OQ-7: Does `pull_jobs.py` already track last-seen?** If it does, B0 shrinks to a backfill check. **Answer in B0 by reading the script.**
