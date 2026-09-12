# dbt Portfolio Project — Roadmap

> Phases are ordered by dependency. Each checkbox is one session (1–3 hours). Each phase ends with something a reviewer could look at. Don't start a phase until the previous exit test passes — a half-built dbt project reads worse than none. Target dates are pacing guides, not deadlines.

## Phase A — Learn the Mental Model
**Goal: know what every dbt noun means by doing it, on someone else's project.**
**Pacing: weekend of Sep 12–13, 2026 (~4 hours total).**

- [ ] **A1 — Jaffle Shop end to end.** Clone `dbt-labs/jaffle_shop_duckdb`, `uv sync`, then `dbt debug` → `dbt seed` → `dbt run` → `dbt test` → `dbt docs generate && dbt docs serve`. Open the lineage graph.
- [ ] **A2 — See what Jinja becomes.** Read `models/customers.sql` next to `target/compiled/.../customers.sql`. Toggle `staging` between `view` and `table` in `dbt_project.yml`, re-run, look at the DuckDB file.
- [ ] **A3 — Add and break.** Write one new mart model with a `ref()`, a description, and a `not_null` test; run `dbt build --select +your_model`. Then add a duplicate id to a seed CSV and watch `unique` fail and halt downstream.
- [ ] **A4 — Rehearse the snapshot.** Add a snapshot on `raw_orders` (check strategy on `status`), run `dbt snapshot`, edit an order's status in the seed, re-seed, re-snapshot, inspect `dbt_valid_from` / `dbt_valid_to`. This is a dress rehearsal for B3.
- [ ] **A5 — Read the spec.** dbt Labs "How we structure our dbt projects" guide, then the dbt SQL style guide. Note anything surprising in `02_DBT_DECISIONS.md` under OQs.
- **Exit test:** explain `ref`, `source`, `seed`, `test`, `snapshot`, `materialization`, and `docs` in one sentence each, without notes. `dbt build` has succeeded on a model you wrote.

## Phase B — Build
**Goal: a complete, tested, documented dbt layer on the job-market pipeline.**
**Pacing: Sep 14 – Oct 4, 2026. One checkbox per session; two sessions a week is plenty.**

### B0 — Prepare the load side
- [ ] Confirm the raw SQLite filename and the `jobs` table schema (`sqlite3 <file> ".schema jobs"`). Paste it into OQ-1 and OQ-2 in the decisions log and resolve them.
- [ ] Add `first_seen_at` and `last_seen_at` to the raw table if absent; `pull_jobs.py` sets `first_seen_at` on insert and bumps `last_seen_at` on every run the posting appears. Backfill existing rows with the API's `created_at` / current run time.
- [ ] Confirm the daily pull is idempotent (run it twice, row count unchanged).
- **Exit test:** every row has `first_seen_at ≤ last_seen_at`; a second run bumps only `last_seen_at`.

### B1 — Scaffold and sources
- [ ] `dbt init` inside the repo as `dbt/` (project name `job_market`), replace the generated example models, write `profiles.yml` with the SQLite attach (see ADR-003), `dbt debug` green.
- [ ] Declare the source (`job_boards.jobs`) with freshness on `last_seen_at`; `dbt source freshness` passes.
- [ ] `packages.yml` with `dbt_utils`; `dbt deps`.
- [ ] `.gitignore` for `target/`, `dbt_packages/`, `logs/`, `*.duckdb`. First commit: "scaffold dbt project".
- **Exit test:** `dbt show --inline "select count(*) from {{ source('job_boards','jobs') }}"` returns the row count.

### B2 — Staging
- [ ] `stg_job_boards__postings`: rename to snake_case, cast types (SQLite via DuckDB attach tends to arrive loosely typed — this is where it gets fixed), trim strings, derive nothing else. Surrogate key via `dbt_utils.generate_surrogate_key(['source','source_job_id'])`.
- [ ] Tests: `unique` + `not_null` on the key; `accepted_values` on `source`; `not_null` on `company`, `title`, `first_seen_at`.
- [ ] Descriptions on every column. Materialized as a view.
- **Exit test:** `dbt build --select staging` green; commit.

### B3 — Snapshot (the story)
- [ ] `snapshots/postings_snapshot.yml` over the source, strategy per ADR-005 (check on content columns: title, location, department, workplace type).
- [ ] Run `dbt snapshot`; confirm the table has `dbt_valid_from` / `dbt_valid_to` / `dbt_scd_id`.
- [ ] Add `dbt snapshot` to the daily workflow (`pull_jobs.py` → `dbt snapshot` → `dbt build` → export). Document the order in the README.
- [ ] After 2–3 days of runs, verify at least one real change was captured (a title or location edit). If nothing has changed yet, that's fine — note the date history started.
- **Exit test:** snapshot table exists and grows only on change; the daily workflow includes it.

### B4 — Intermediate models and macros
- [ ] `macros/classify_workplace.sql`: remote / hybrid / onsite from Lever's workplace field where present, regex on title + location otherwise (OQ-5).
- [ ] `int_postings__classified`: staging + workplace type + seniority bucket + normalized location (city/state/country split).
- [ ] `int_postings__lifecycle`: `is_active` (`last_seen_at` = latest run), `closed_at` (`last_seen_at` when inactive), `days_open`.
- [ ] Unit tests (dbt ≥1.8 `unit_tests:`) on the classification logic: five title/location fixtures → expected labels.
- **Exit test:** `dbt build --select intermediate` green including unit tests; commit.

### B5 — Marts
- [ ] `seeds/company_metadata.csv` (industry, HQ, size bucket for the 15 companies) — hand-curated, documented as such.
- [ ] `dim_companies`: seed joined to observed posting counts, first/last posting dates.
- [ ] `fct_job_postings`: one row per posting — company, title, workplace type, seniority, location, `first_seen_at`, `closed_at`, `is_active`, `days_open`.
- [ ] `fct_postings_open_daily`: `dbt_utils.date_spine` × company, count of postings open on each day (range join on `first_seen_at` / `closed_at`).
- [ ] `fct_posting_changes`: from the snapshot — one row per change with before/after values and valid range.
- [ ] Contracts (`contract: enforced`) on all marts; `relationships` tests from facts to `dim_companies`; singular test `assert_closed_after_opened.sql`.
- [ ] Marts materialized as tables; document the materialization choice per model in the YAML description.
- **Exit test:** `dbt build` green end to end; `fct_postings_open_daily` answers "how many open roles did company X have on date Y".

### B6 — Docs and exposures
- [ ] Every model and column has a description; `dbt docs generate` shows zero undocumented columns.
- [ ] `exposures.yml`: the Streamlit app and Tableau dashboard as exposures depending on the marts.
- [ ] `dbt docs generate --static` → single-file `index.html`; GitHub Actions publishes it to GitHub Pages on merge to main.
- [ ] README links to the docs site; lineage graph screenshot in the README.
- **Exit test:** docs URL loads from a phone with the lineage graph visible.

### B7 — CI and lint
- [ ] Decide CI data per OQ-3 (lean: commit a small sample SQLite under `dbt/sample/`).
- [ ] `.github/workflows/dbt.yml`: `uv sync` → `dbt deps` → `dbt build --target ci` on every PR. `ci` target in `profiles.yml` attaches the sample DB.
- [ ] `sqlfluff` with the dbt templater; `pre-commit` hook; fix everything it flags.
- [ ] Green badge in the README.
- **Exit test:** a PR that breaks a test fails CI; a clean PR passes.

### B8 — Wire the consumers
- [ ] `export_for_tableau.py` reads `fct_job_postings` and `fct_postings_open_daily` from the DuckDB file instead of raw SQL.
- [ ] `app.py` reads from marts; add one chart only `fct_postings_open_daily` makes possible (open roles over time).
- [ ] README rewrite: architecture diagram (Mermaid), "why dbt" paragraph, run instructions, badges, screenshot.
- **Exit test (phase):** fresh clone → `uv sync` → `dbt build` → `dbt docs generate` → `streamlit run app.py` in under 10 minutes; dashboard shows the time-series chart.

## Phase C — Tell the Story
**Goal: the project earns its place on the resume and survives an interview.**
**Pacing: Oct 5–10, 2026.**

- [ ] Resume bullet(s), written against the honesty rules; names dbt, snapshots, tests, docs, CI; links the repo.
- [ ] 10-minute demo script: problem (history lost) → snapshot → open-postings-per-day → lineage → tests catching something real.
- [ ] Interview drill: whiteboard the DAG; explain view vs table vs incremental and why nothing here is incremental (data is small — and say so).
- [ ] Optional: short LinkedIn post with the lineage screenshot.
- **Exit test:** run the demo script cold in under 10 minutes without opening the docs.

## Phase D — Stretch / Unscheduled (pull up only on real need)
- Upgrade to dbt Core 2.0 once GA — its own one-session milestone, after Phase B
- Incremental materialization on `fct_posting_changes` (only if the snapshot grows enough to justify it)
- `dbt-expectations` package for distribution tests
- One Python model (dbt-duckdb supports them) — only if there's real logic SQL can't express
- Steam data as dbt project #2 (game-analytics lane): needs daily playtime captures accumulating first
- Feed real usage back into DAT's parking-lot "dbt helper utilities" idea

## Anti-Roadmap (so we ship)
- No dbt platform / dbt Cloud account
- No Postgres, Snowflake, or BigQuery — DuckDB is the point
- No new companies or API sources until Phase B ships
- No dashboard redesign before marts exist
- No dbt Core 2.0 migration mid-build
- No semantic layer, no metrics YAML
- No second dbt project before the first one has a green badge
