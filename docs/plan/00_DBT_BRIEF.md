# dbt Portfolio Project — Brief

> **Status:** Living document. Anchor for every decision in this project. Same rule as DAT: if a proposed step conflicts with this brief, the brief wins or gets deliberately amended. Sister docs: `01_DBT_ROADMAP.md` (what to do, in order) and `02_DBT_DECISIONS.md` (why).

## The One-Sentence Version

Add a dbt transformation layer to the existing `job-market-pipeline` repo so it becomes a complete, reproducible ELT stack — Python extract/load → **dbt transform (DuckDB)** → Tableau/Streamlit — that closes the biggest gap on the resume with real data and a true story.

## Why This Exists

1. **The resume gap.** Every analytics-engineering, BI, and modern RevOps posting lists dbt. Nothing on the resume demonstrates it. This project is the fix, and it has to be real enough to survive a 10-minute interview drill-down.
2. **The existing pipeline has a real problem dbt solves.** `pull_jobs.py` upserts daily, so posting history is overwritten. "How long was this role open? When did the title change?" is unanswerable today. dbt snapshots (SCD Type 2) are the canonical answer. That is the interview story, and it is true.
3. **Learning by building beats learning by watching.** The Jaffle Shop tutorial teaches vocabulary; wiring dbt into a pipeline you already own teaches judgment (what goes in staging, when to snapshot, what to test).

## What a Reviewer Actually Checks (the rubric)

A hiring manager gives a portfolio repo about five minutes. Every item below is a checkbox they tick or don't. The roadmap is built to hit all ten.

| # | They look for | Where it lives |
|---|---|---|
| 1 | README with an architecture diagram, a one-paragraph "why", and copy-paste run instructions | `README.md` |
| 2 | Layered models: `staging/` → `intermediate/` → `marts/`, dbt Labs naming (`stg_`, `int_`, `fct_`, `dim_`) | `dbt/models/` |
| 3 | Every model has a description; every primary key has `unique` + `not_null` | `_*__models.yml` |
| 4 | Sources declared in YAML with freshness checks | `_*__sources.yml` |
| 5 | At least one snapshot (or incremental model) — proof you understand state over time | `dbt/snapshots/` |
| 6 | A non-trivial macro and at least one package (`dbt_utils`) | `dbt/macros/`, `packages.yml` |
| 7 | Modern features: unit tests on logic, contracts on marts | `_marts__models.yml` |
| 8 | Docs site live with a lineage graph, reachable from the README in one click | GitHub Pages |
| 9 | CI running `dbt build` on every PR, green badge | `.github/workflows/` |
| 10 | A commit history that shows iteration, not one giant "add dbt" commit | `git log` |

Plus the verbal test: explain view vs table vs incremental, and why each model got the materialization it did.

## Design Principles

1. **Zero infrastructure.** dbt Core + dbt-duckdb. No warehouse account, no dbt platform account, no credentials. A reviewer can clone and `dbt build` in under two minutes.
2. **Real data, public data.** Job postings from public boards. No employer data, no personal data. The raw SQLite can be committed or sampled without a scrub step.
3. **The loader is not the project.** `pull_jobs.py` changes only where dbt needs it to (adding `first_seen_at` / `last_seen_at`). Everything else is transformation.
4. **Follow dbt Labs conventions exactly.** "How we structure our dbt projects" and the dbt SQL style guide are the spec. Reviewers pattern-match against them; originality here is a liability.
5. **Every step ships something inspectable.** A model, a test, a docs page. No milestone ends in "refactored".
6. **Honest story.** Resume bullets and the README describe what was built and what it solved. Nothing inflated (see the resume honesty rules in the Résumé Builder project).

## Scope

### In scope
- dbt project inside `job-market-pipeline` at `dbt/`, built on dbt Core 1.12.x + dbt-duckdb
- Sources → staging → intermediate → marts for job postings, companies, and daily open-posting counts
- Snapshots for posting history; closure detection via `last_seen_at`
- Tests (generic, singular, unit), contracts on marts, docs, exposures, CI
- Re-pointing the Streamlit app and Tableau export at mart tables
- README rewrite so the repo reads as one ELT system

### Out of scope (deliberate)
- dbt platform / dbt Cloud — not needed, adds nothing a reviewer checks
- Any real warehouse (Postgres, Snowflake, BigQuery) — same reason; DuckDB is the point
- New API sources or companies — the data is sufficient; scope goes to dbt, not ingestion
- Semantic layer / MetricFlow — reviewers don't check it; it's a rabbit hole
- Migrating to dbt Core 2.0 mid-build — upgrade after Phase B ships, as its own small milestone
- Dashboard redesign — the dashboard changes only in *where it reads from*

## Relationship to Other Projects

- **`job-market-pipeline`** is the host repo. These three planning docs live at `docs/plan/` in that repo and in that project's Claude Project knowledge so every session has context.
- **DAT** is a separate repo and stays that way (its brief already says DAT complements dbt stacks, not competes). DAT's Phase 0 PyPI namespace claim still happens — one short session — then DAT Phase 1 waits until this project's Phase B ships.
- **Steam data** is the candidate for dbt project #2 (game-analytics lane), once dbt is learned. Not before.

## Target Repo Layout (end of Phase B)

```
job-market-pipeline/
├── README.md                   # architecture diagram, why dbt, how to run, badges
├── pull_jobs.py                # existing EL — gains first_seen_at / last_seen_at
├── export_for_tableau.py       # existing — reads from marts instead of raw SQL
├── app.py                      # existing Streamlit — reads from marts
├── companies.json              # existing config
├── jobs.db                     # existing raw SQLite (filename TBD — confirm in B0)
├── docs/
│   ├── plan/                   # these three docs
│   └── screenshot.png
├── dbt/                        # ← the dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml            # committed — local paths only, no secrets
│   ├── packages.yml            # dbt_utils
│   ├── job_market.duckdb       # gitignored build target
│   ├── models/
│   │   ├── staging/job_boards/
│   │   │   ├── _job_boards__sources.yml
│   │   │   ├── _job_boards__models.yml
│   │   │   └── stg_job_boards__postings.sql
│   │   ├── intermediate/
│   │   │   ├── _int__models.yml
│   │   │   ├── int_postings__classified.sql
│   │   │   └── int_postings__lifecycle.sql
│   │   └── marts/
│   │       ├── _marts__models.yml
│   │       ├── dim_companies.sql
│   │       ├── fct_job_postings.sql
│   │       ├── fct_postings_open_daily.sql
│   │       └── fct_posting_changes.sql
│   ├── snapshots/
│   │   └── postings_snapshot.yml
│   ├── seeds/
│   │   └── company_metadata.csv    # hand-curated: industry, HQ, size bucket
│   ├── macros/
│   │   └── classify_workplace.sql
│   ├── tests/
│   │   └── assert_closed_after_opened.sql
│   └── analyses/
└── .github/workflows/
    └── dbt.yml                 # dbt build on PR against sample data
```

Model names are the plan, not a contract — OQ-1 in the decisions log covers whether staging splits per source once the raw schema is confirmed.

## Success Criteria

- **Four weeks (target: ~Oct 10, 2026):** Phase B exit test passes — clean clone → `uv sync` → `dbt build` green → docs live → dashboard reads from marts, in under 10 minutes.
- **Portfolio test:** a reviewer gets from the README to the lineage graph in two clicks and can name the snapshot's purpose from the README alone.
- **Interview test:** you can whiteboard the DAG and explain the snapshot strategy, the materialization choices, and one test that caught something — without notes.
- **Resume test:** one honest bullet on the resume that names dbt, snapshots, tests, and docs, and points at the repo.

## Session Protocol (same as DAT)

1. **Start:** name the roadmap checkbox being worked. Claude works from these docs plus that statement.
2. **During:** a design choice that contradicts a decision means stop and either follow it or write a superseding one.
3. **End:** tick boxes, append decisions, resolve open questions. The docs leave every session true.
