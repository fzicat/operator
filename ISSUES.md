# TradeTools / Operator — Issue Analysis (Phase 2)

Date: 2026-06-12. Builds on `AUDIT.md` (Phase 1) and the owner's answers to its §10 questions.
Severity: **Critical** = act now / data or credential exposure · **High** = real correctness/security risk · **Medium** = should fix during refactor · **Low** = polish.

Global constraint applying to every proposed fix: **no operation may modify or delete data
in the live Supabase database.** Schema changes ship as user-run SQL scripts.

---

## 1. Security

| # | Sev | Finding | Location | Proposed fix |
|---|---|---|---|---|
| S1 | **Critical** | `t.sh` stores a real email + password in plaintext and passes them via argv (visible in `ps`, shell history) | `t.sh:4`, enabled by `-p/--password` flag in `main.py:227-228` | Delete `t.sh`; remove the `-p` flag; support `TT_PASSWORD` env var (or prompt-only) for auto-login. *(Approved.)* **Rotate the exposed password.** |
| S2 | **Critical** | RLS grants ALL operations to *any* authenticated user, the anon key is public by design, and the app is deployed on Vercel — if Supabase email signups are enabled (the default), a stranger can register and read/write all financial data | `scripts/supabase_schema.sql:131-147`; Vercel deployment | Verify in the Supabase dashboard that public signups are disabled (action for owner — cannot be confirmed from code); document the requirement in README. |
| S3 | **High** | Trade import prints the Flex download URL **including the IBKR token** to the terminal (scrollback/log leak) | `cli/ibkr_module.py:561` (`print(url_dl)`) | Delete the `print`. |
| S4 | **High** | `next@16.1.4` has three published advisories (DoS via image optimizer, RSC deserialization DoS, HTTP request smuggling in rewrites); 8 npm vulnerabilities total (4 high) | `web/package.json:13`; `npm audit` | Upgrade to `next@16.2.x`, run `npm audit fix`; re-run build + smoke test. |
| S5 | **Medium** | CLI uses the **service-role key** for all DB access, making RLS decorative and keeping an all-powerful secret on the laptop; email/password login is performed but its session is unused for data access | `shared/supabase_client.py:9-16`, `shared/config.py:10` | Optional (needs approval): authenticate the supabase-py client with the anon key + user session so the CLI obeys RLS; service-role key then only needed for admin scripts. |
| S6 | **Medium** | Python dependencies unpinned (`requirements.txt`), so installs are unreproducible and unauditable; `ib-insync` upstream is archived/unmaintained | `cli/requirements.txt` | Pin exact known-good versions (incl. `ib-insync==0.9.86`); note `ib_async` fork as a future migration (separate approval — new dependency). |
| S7 | **Low** | HTTP requests to IBKR Flex have no timeout — a hang blocks the CLI indefinitely (availability, not confidentiality) | `cli/ibkr_module.py:540,566`; also yahooquery calls | Add explicit `timeout=` to `requests.get` calls. |
| S8 | **Low** | Real personal financial data is committed to git (`ibkr_performance_2026.csv`, bitcoin seed migration) | `cli/data/`, `scripts/migrations/20260607_add_bitcoin.sql` | Acknowledged by owner — no action; keep repo private. |

## 2. Bugs & correctness

| # | Sev | Finding | Location | Proposed fix |
|---|---|---|---|---|
| B1 | **High** | **CLI/web MTM drift**: CLI was changed (commit `cedca49`) so MTM Value/MTM % count *shares only*, but the web still includes call/put MTM in position `mtm`, `mtmPercent`, and `totalMtm` — the two UIs show different numbers for the same portfolio | `web/src/lib/utils/fifo.ts:438-442` vs `cli/ibkr_module.py:1413-1414` | Align web `calculatePositions` to stock-only MTM (behavior change — needs approval). |
| B2 | **High** | **FBN save is delete-then-insert, non-atomic**: if the insert fails after the delete, the month's row is lost; also churns row `id`s | `cli/db/fbn_db.py:33-39`, `web/src/app/(authenticated)/fbn/entry/page.tsx:80-95` | Replace with a single `upsert(..., on_conflict="date,account")` in both apps. *(Approved.)* |
| B3 | **High** | **Web FBN entry can silently zero a month**: the form never loads existing values (CLI does), so re-submitting an existing (date, account) overwrites real data with zeros; USD accounts also default `rate: 0` | `web/.../fbn/entry/page.tsx:35-65` (rate 0 at line 64) | Pre-load existing row into the form; default USD rate to 1 or make it required-nonzero; confirm before overwrite. |
| B4 | **Medium** | **Zero-rate footgun propagates**: CLI aggregation multiplies USD rows by `rate` with no guard, so a stored `rate=0` (possible via B3) silently erases that account from every CLI total; web guards with `rate \|\| 1`, so CLI and web disagree | `cli/fbn_module.py:42-44` vs `web/.../fbn/page.tsx:34-36` | Pick one rule (suggest: treat 0/null rate as 1 + warn) and apply in both apps. |
| B5 | **Medium** | Trade timestamps are NY wall time stored in TIMESTAMPTZ as if UTC; both UIs patch it in the view layer (`parseAsNY`, `tz_localize(None)`) — fragile, and any new consumer will get times 4–5 h off | schema `trades.date_time`; `web/src/lib/utils/format.ts:29-54`; multiple CLI call sites | Do **not** migrate data (DB is off-limits); centralize and document the convention (one Python helper + the existing TS helper), and have import normalize consistently going forward. |
| B6 | **Medium** | DB layer swallows errors with `print(...)` and returns empty results — a Supabase outage looks like "Trades loaded: 0" instead of an error | `cli/db/ibkr_db.py:115-117` and all `cli/db/*.py` except handlers | Use `logging` + surface failures to the UI (distinguish "no data" from "fetch failed"). |
| B7 | **Medium** | CSP exposure hardcodes contract multiplier `100` instead of the row's `multiplier` | `cli/ibkr_module.py:1841`, `cli/ibkr_stats_submodule.py:356` | Use `row['multiplier']` with 100 fallback (no visible change for standard contracts). |
| B8 | **Low** | `datetime.utcfromtimestamp()` is deprecated (warns on Python 3.12+, scheduled for removal) | `cli/providers/yahoo_equity_provider.py:53` | `datetime.fromtimestamp(ts, tz=timezone.utc)`. |
| B9 | **Low** | Free-text fallbacks in CLI entry flows let typos create new account/category/exchange values (data quality) | `cli/equity_module.py:124-137`, `cli/bitcoin_module.py:118,131` | Validate against the known constant lists; reject unknown values. |
| B10 | **Low** | `edit_trade` delta shorthand (`"5"` → 0.5, `"25"` → 0.25) is surprising and undocumented | `cli/ibkr_module.py:917-926` | Document in the prompt text (keep behavior). |
| B11 | **Low** | `show_performance` computes `stock_value`/`stock_mtm` that are never displayed | `cli/ibkr_module.py:307-308` | Delete the two dead locals. |
| B12 | **Low** | ESLint `react-hooks/set-state-in-effect` in ThemeProvider (cascading-render pattern) | `web/src/lib/theme.tsx:24-28` | Initialize from `localStorage` via lazy `useState` initializer (same visible behavior). |
| B13 | **Low** | `prefer-const` lint errors | `web/src/lib/utils/fifo.ts:72`, `web/src/lib/utils/format.ts:39` | `let` → `const`. |

## 3. Dead code & cruft

All confirmed unreferenced by grep; removals are behavior-neutral. (`margin_requirements` is **excluded** — owner keeps it for a future feature.)

| # | Sev | Finding | Location | Proposed fix |
|---|---|---|---|---|
| D1 | **Medium** | Dead duplicate FIFO engine (~100 lines) + its private helper — third copy of the P&L logic, guaranteed to drift | `cli/ibkr_module.py:71-170` (`calculate_pnl`), `:22-42` (`_parse_option_expiry`) | Delete (canonical lives in `cli/services/quote_service.py`). |
| D2 | **Medium** | Legacy `market_price` accessors (table superseded by `market_quotes`) | `cli/db/ibkr_db.py:120-151` | Delete; ship `scripts/migrations/20260612_drop_market_price.sql` for the owner to run **manually**. *(Approved.)* |
| D3 | **Medium** | `scripts/migrate_to_supabase.py` — one-time migration, now broken (`DB_PATH` no longer exists in `shared.config`) | `scripts/migrate_to_supabase.py:20` | Delete. |
| D4 | **Medium** | `cli/quote_refresh.py` — "invoked from the web app", but nothing calls it (owner confirmed) | whole file | Delete. |
| D5 | **Low** | Unused auth helpers; `is_authenticated` imported but never called | `shared/supabase_client.py:31-56`, `cli/main.py:12` | Delete functions + trim import. |
| D6 | **Low** | `SUPABASE_ANON_KEY` loaded by CLI config, never used | `shared/config.py:11` | Delete (unless S5 option is approved, which would start using it). |
| D7 | **Low** | `valuation_service.calculate_position_totals` never called | `cli/services/valuation_service.py:59-79` | Delete. |
| D8 | **Low** | Icon-generation leftovers inside app source (tracked) | `web/src/app/apply_mask.py`, `icon copy.png`, `icon-sample.png`, `favicon.ico.bak` | Delete. |
| D9 | **Low** | Empty root `package-lock.json` (no root package.json) | `package-lock.json` | Delete. |
| D10 | **Low** | `t.bat` tracked although `.gitignore` lists it | `t.bat`, `.gitignore:8` | `git rm --cached t.bat` (keep local file). |
| D11 | **Low** | Likely-unused TS types `MarketPrice`, `PositionDetail`; unused `Select` import | `web/src/types/index.ts:75,59`; `web/.../fbn/entry/page.tsx:10` | Verify with grep, then delete. |
| D12 | **Low** | Web `applyMtmPrices` legacy price-map branch — no live caller passes plain price maps anymore | `web/src/lib/utils/fifo.ts:390-411` | Collapse pages onto `applyMarketQuotes`; remove the heuristic wrapper. |
| D13 | **Low** | Stale comment "for SQLite" | `cli/equity_module.py:354` | Delete comment. |

## 4. Architecture & design

| # | Sev | Finding | Location | Proposed fix |
|---|---|---|---|---|
| A1 | **High** | Finance math duplicated Python↔TypeScript with no parity guard (B1 is the first observed drift) | `cli/services/quote_service.py` ↔ `web/src/lib/utils/fifo.ts` | Pin parity with **shared golden test fixtures** (one JSON file consumed by both pytest and vitest); document the pair as "must change together". |
| A2 | **High** | `symbol_targets` table absent from the schema script — DB cannot be rebuilt from the repo | `scripts/supabase_schema.sql` | Add the DDL (owner provided live schema) + `scripts/migrations/20260612_add_symbol_targets.sql`. |
| A3 | **Medium** | `ibkr_module.py` is a 2 021-line god module mixing data prep, aggregation, and Rich rendering; per-symbol aggregation is re-implemented 4× (`list_all_positions`, `list_positions_by_basket`, `list_csp`, `list_positions_csv`) | `cli/ibkr_module.py:1335-2016` | Extract one `aggregate_positions(trades_df, ...)` into `cli/services/`; views only render. |
| A4 | **Medium** | Daily/weekly stats series logic duplicated between module and stats submodule | `cli/ibkr_module.py:1161-1292` vs `cli/ibkr_stats_submodule.py:90-120` | Single series helper used by tables and plots. |
| A5 | **Medium** | Every IBKR web page repeats the same fetch→camelCase→filter→FIFO→quotes pipeline and a verbatim ~25-line sort handler (6+ copies) | `web/src/app/(authenticated)/ibkr/*/page.tsx` | Extract `useProcessedTrades()` / `usePositions()` and `useSortable()` hooks. |
| A6 | **Medium** | Three copy-pasted dropdown menus differing only in items/label | `web/src/components/layout/{IBKR,Equity,Bitcoin}Menu.tsx` | One generic `ModuleMenu({label, items})`. |
| A7 | **Medium** | Mixed import styles in CLI (`from base_module import` vs `from cli.db import`) relying on a `sys.path` hack — fragile dual import identity | `cli/main.py:6`, `cli/ibkr_module.py:14-16` etc. | Standardize on `cli.`-absolute imports; keep `python cli/main.py` working. |
| A8 | **Low** | `export const supabase = ... : null!` is a runtime landmine for any future server-side import | `web/src/lib/supabase.ts:26` | Replace direct export usage with `getSupabaseClient()` (or throw with a clear message server-side). |
| A9 | **Low** | Shared business constants (FBN accounts, categories, exchanges) duplicated Python↔TS | `web/src/types/index.ts:246-281` ↔ `cli/fbn_module.py:22-32`, `cli/equity_module.py`, `cli/bitcoin_module.py` | Document as intentionally duplicated with cross-references (codegen is overkill here). |
| A10 | **Low** | `refresh_mtm_quotes` returns `quotes` as a mix of `QuoteRecord` objects and dicts, forcing callers to type-sniff | `cli/services/quote_service.py:307-309`, consumed at `cli/ibkr_module.py:180-186` | Normalize to dicts before returning. |

## 5. Performance

| # | Sev | Finding | Location | Proposed fix |
|---|---|---|---|---|
| P1 | **Medium** | Equity page refetches the entire `equity` table every time the date dropdown changes (`selectedDate` is in `loadData`'s dependency array) | `web/.../equity/page.tsx:79` | Fetch once; derive the date subset client-side. |
| P2 | **Low** | Every IBKR page downloads the full `trades` + `market_quotes` tables (incl. heavy `raw_payload` JSONB) on each visit; grows unboundedly with trade history | all IBKR pages; `market_quote_db.fetch_latest_quotes` similarly | Select only needed columns for quotes; share one fetch via the A5 hook; acceptable for current single-user scale. |
| P3 | **Low** | `calculate_pnl`/`apply_quotes` use `iterrows()` row loops | `cli/services/quote_service.py:67`, `valuation_service.py:20` | Leave as-is (clear and fast enough at this scale); revisit only if slow. |

## 6. Maintainability

| # | Sev | Finding | Location | Proposed fix |
|---|---|---|---|---|
| M1 | **High** | **Zero tests** anywhere — financial calculations have no safety net (this is what allowed B1 to drift unnoticed) | repo-wide | Add pytest + vitest characterization tests around FIFO/credit/premium/aggregation **before** any restructuring. *(Approved.)* |
| M2 | **High** | CLAUDE.md / README.md / AGENTS.md describe deleted routes, API endpoints, components, and the pre-quote-pipeline architecture — actively misleading for humans and agents | `CLAUDE.md`, `README.md`, `AGENTS.md` | Rewrite after the refactor lands (final step), incl. removing `IBKR_TOKEN`/`QUERY_ID_DAILY`/`PYTHON_BIN` from web env docs *(approved obsolete)*. |
| M3 | **Medium** | `web/README.md` is untouched create-next-app boilerplate | `web/README.md` | Replace with 10 lines of real instructions (or delete in favor of root README). |
| M4 | **Medium** | No lint/format tooling for Python; no CI for either app | repo-wide | Add `ruff` (lint+format, dev-only) and a minimal `lint+test+build` script; CI optional for a private repo. |
| M5 | **Low** | Hardcoded 2026 dates and `ibkr_performance_2026.csv` | `cli/ibkr_module.py:1182,1253`, `ibkr_stats_submodule.py:100,116`, web stats/premium pages | **Intentional** annual convention — no change now; owner will deal with it in **December 2026**. Centralize the constant per app so December's edit is one line each. |
| M6 | **Low** | Type hints absent in the older CLI modules (newer `services/`/`domain/` are typed) | `cli/ibkr_module.py`, `fbn_module.py`, `equity_module.py`, `bitcoin_module.py` | Add hints opportunistically while touching code; don't blanket-rewrite. |
| M7 | **Low** | `web/tsconfig.tsbuildinfo` untracked build artifact not ignored | `web/.gitignore` | Add to ignore list. |

---

## Cross-cutting note for Phase 3

The single most valuable structural fix is **A1/M1**: shared golden fixtures pinning the
Python and TypeScript FIFO engines to identical outputs. Nearly every High item here
(B1, B2, B3, A3, A5) becomes safe to fix once those tests exist.
