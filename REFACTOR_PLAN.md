# TradeTools / Operator — Refactor Plan (Phase 3)

Date: 2026-06-12. Derived from `AUDIT.md` + `ISSUES.md` and the owner's Q&A answers.
**No code changes until this plan is approved.**

## Ground rules (non-negotiable, apply to every step)

1. **The live Supabase database is never written to or deleted from by me.** All schema
   changes are delivered as SQL files in `scripts/migrations/` for the owner to run.
   Tests are pure-function tests with no Supabase client. CLI/web smoke checks use
   read-only commands only.
2. The app stays functional after every step; each step is one commit.
3. Behavior is preserved except for the explicitly listed changes in §4, each requiring
   individual approval.

---

## 1. Target architecture

The current shape is fundamentally sound for a single-user, two-frontend app. The plan
**keeps** the structure and removes the rot — no new frameworks, no rewrite.

```
operator/
├── cli/
│   ├── main.py / base_module.py / tui.py        # shell (unchanged shape)
│   ├── *_module.py                              # thin command routers + Rich rendering only
│   ├── services/                                # ALL business math lives here
│   │   ├── quote_service.py                     # FIFO, credit, contract keys, quote refresh (existing)
│   │   ├── valuation_service.py                 # quote application (existing)
│   │   └── position_service.py                  # NEW: per-symbol aggregation used by all list views
│   ├── providers/ · domain/ · db/               # unchanged boundaries
│   └── data/
├── shared/                                      # Python config + Supabase client
├── tests/                                       # NEW: pytest (pure functions only)
│   └── fixtures/fifo_golden.json                # shared with vitest — parity contract
├── web/
│   └── src/
│       ├── app/(authenticated)/**/page.tsx      # thin pages
│       ├── components/ui/ · layout/ModuleMenu   # one generic menu replaces three copies
│       ├── lib/hooks/                           # NEW: useProcessedTrades, usePositions, useSortable
│       ├── lib/utils/fifo.ts (+ __tests__/)     # vitest, consumes the same golden fixtures
│       └── ...
├── scripts/
│   ├── supabase_schema.sql                      # now complete (symbol_targets added)
│   └── migrations/                              # additive, user-run
└── README.md / ARCHITECTURE.md / CHANGELOG.md   # rewritten at the end
```

Decisions and one-line justifications:

- **Keep the Python↔TS duplication of FIFO math, but pin it with shared golden fixtures.**
  Eliminating it would require a server side the web app deliberately doesn't have; tests
  make the duplication safe, which is the actual problem.
- **CLI views render; services compute.** The four copies of per-symbol aggregation in
  `ibkr_module.py` collapse into one `position_service.aggregate_positions()`; same data,
  same numbers, less drift surface.
- **Web pages share hooks instead of copy-paste.** `useProcessedTrades` (fetch + FIFO +
  quotes once), `usePositions`, `useSortable`, and a generic `ModuleMenu` — boring React,
  no state library.
- **Imports standardized to `cli.`-absolute** so there is one module identity; the
  `python cli/main.py` entry keeps working via the existing path bootstrap.
- **Tooling added is dev-only and approved:** `pytest`, `vitest`, plus `ruff` for Python
  lint/format (zero-config, no runtime impact). Nothing else.
- **Hardcoded 2026 dates stay** (owner decision, revisit December 2026) but are
  centralized to one constant per app so December's change is two lines.

## 2. Execution steps

Each step = one commit. "Verify" = the full check set available at that point:
`pytest` · `ruff check` · `npx tsc --noEmit` · `npm run lint` · `npm run build` · `vitest run`.

### Step 0 — Safety net snapshot
- **What:** Tag current state (`git tag pre-refactor`).
- **Break risk:** none. **Verify:** tag exists.

### Step 1 — Test infrastructure + characterization tests (M1, A1)
- **What:** Add `pytest` + `ruff` (dev requirements file), `vitest` (web devDependency).
  Write characterization tests pinning **current** behavior of:
  - Python: `quote_service.calculate_pnl/calculate_credit/prepare_trades`,
    `domain/contracts` key building, `valuation_service.apply_quotes`,
    FBN `_aggregate`, equity derived columns, performance-CSV parsing.
  - TS: `calculatePnL`, `calculateCredit`, `buildContractKey`, `applyMarketQuotes`,
    `calculateClosedOpenPremium`, `calculateOutstandingPremiumByDay`,
    `calculatePositions`, `parseAsNY`.
  - **Shared golden fixture** (`tests/fixtures/fifo_golden.json`): synthetic trade
    sequences (partial closes, over-close sign flips, options w/ multipliers) with
    expected realized/remaining/credit — consumed by both pytest and vitest, proving the
    two engines agree. Fixtures are synthetic; **no DB access anywhere in tests**.
- **Break risk:** none (additive). **Verify:** all tests green on unmodified code.

### Step 2 — Dead code & cruft removal (D1–D13, B11)
- **What:** Delete: dead CLI `calculate_pnl` + `_parse_option_expiry`; legacy
  `market_price` accessors; `migrate_to_supabase.py`; `quote_refresh.py`; unused auth
  helpers + `SUPABASE_ANON_KEY` (config); `calculate_position_totals`; icon cruft +
  `apply_mask.py`; root `package-lock.json`; unused TS types/imports/locals; legacy
  `applyMtmPrices` price-map branch (pages call `applyMarketQuotes`); stale comments.
  `git rm --cached t.bat`; ignore `tsconfig.tsbuildinfo`.
  **Kept deliberately:** `margin_requirements` fetch (future feature — annotated as such).
- **Break risk:** a missed hidden reference → import error. **Verify:** full check set;
  grep for every deleted symbol; CLI import smoke (`python -c "import cli.main"`).

### Step 3 — Security fixes (S1, S3, S4, S6, S7)
- **What:** Delete `t.sh`; remove `-p/--password` flag, add `TT_PASSWORD` env-var
  fallback for auto-login; delete the token-URL `print`; add `timeout=30` to Flex
  requests; pin `requirements.txt`; upgrade `next` to 16.2.x + `npm audit fix`;
  document the "Supabase signups must be disabled" requirement (S2 is an owner action).
- **Break risk:** Next minor upgrade could affect build/runtime. **Verify:** full check
  set; `npm run build`; `npm audit` re-run; manual click-through after deploy preview.

### Step 4 — Approved bug fixes (B1–B4, B7, B8, B12, B13)
- **What:** One commit per fix:
  4a. FBN upsert (CLI `fbn_db.save_account_entry` + web entry submit) on
      `(date, account)` — **client-side code change only**; requires no schema change
      (unique constraint already exists).
  4b. Web FBN entry pre-loads existing values; USD rate default 1 / required-nonzero;
      explicit overwrite notice.
  4c. Zero-rate guard: CLI and web both treat rate 0/null as 1 during aggregation (warn).
  4d. Align web MTM to stock-only (`calculatePositions`), matching CLI commit `cedca49`;
      update golden fixtures intentionally.
  4e. CSP multiplier from row data; Yahoo `utcfromtimestamp` modernization; ThemeProvider
      effect fix; `prefer-const` fixes.
- **Break risk:** 4a–4d change user-visible numbers/flows (all listed in §4). **Verify:**
  updated tests + full check set; FBN upsert exercised only in tests via mocked client —
  **no live DB writes**.

### Step 5 — Schema & docs sync (A2, S2-doc, M2 partial)
- **What:** Add `symbol_targets` DDL (owner-provided) to `supabase_schema.sql` +
  `scripts/migrations/20260612_add_symbol_targets.sql`; write
  `scripts/migrations/20260612_drop_market_price.sql` (**user-run, never executed by me**);
  fix `.env.example` and README env sections (drop obsolete web IBKR vars).
- **Break risk:** none (SQL files are inert until the owner runs them). **Verify:** SQL
  reviewed against the owner-provided schema; full check set.

### Step 6 — Web restructure (A5, A6, A8, P1, P2, D12 remainder)
- **What:** `ModuleMenu` generic component (3 menus → 1); `useSortable` hook;
  `useProcessedTrades`/`usePositions` hooks consumed by all IBKR pages; equity page
  fetch-once fix; `market_quotes` column selection (drop `raw_payload` from page fetches);
  remove `null!` supabase export pattern from new code paths.
- **Break risk:** subtle rendering/sort regressions. **Verify:** vitest + tsc + lint +
  build; per-page manual comparison against pre-refactor numbers (read-only).

### Step 7 — CLI restructure (A3, A4, A7, A10, B6)
- **What:** Extract `position_service.aggregate_positions()` and use it from
  `list_all_positions`, `list_positions_by_basket`, `list_csp`, `list_positions_csv`,
  `list_position`; single daily/weekly series helper shared by stats + plots; standardize
  `cli.`-absolute imports; normalize `refresh_mtm_quotes` return type; replace db-layer
  `print` with `logging` + visible UI errors; centralize the 2026 date constants.
- **Break risk:** highest of the plan — table outputs must stay byte-comparable. **Verify:**
  pytest (aggregation now unit-tested), import smoke, manual read-only comparison of `l`,
  `lq`, `lz`, `lb`, `csp`, `csv`, `sd`, `sw` outputs against `pre-refactor` tag.

### Step 8 — Polish & hints (M5, M6, B9, B10)
- **What:** Type hints on touched CLI modules; input validation against constant lists in
  equity/bitcoin entry; delta-shorthand prompt documentation; ruff format pass.
- **Break risk:** low. **Verify:** full check set.

### Step 9 — Phase 5 handover
- **What:** Coverage report (pytest-cov, vitest --coverage) + tests for any uncovered
  critical path; final security pass (`npm audit`, secret grep, input-validation review);
  rewrite `README.md`, write `ARCHITECTURE.md` + `CHANGELOG.md`; update `CLAUDE.md` and
  `AGENTS.md` to the post-refactor reality.
- **Verify:** full check set; docs match `git ls-files` reality.

## 3. What is explicitly out of scope

- Migrating stored timestamps or any other **data** change (DB is read-only to me).
- Switching `ib-insync` → `ib_async` (new dependency — separate proposal if wanted).
- Re-adding web import/MTM (owner confirmed CLI-only is permanent).
- The December 2026 date/CSV rollover (owner handles in December).
- CI pipeline (optional; can be added later in minutes if wanted).

## 4. Behavior changes requiring individual approval

| # | Change | Visible effect | Issue |
|---|---|---|---|
| BC1 | FBN save becomes a true upsert (CLI + web) | Row `id` stops changing on re-save; save is atomic. No stored values change. | B2 |
| BC2 | Web FBN entry pre-loads existing values, USD rate defaults to 1 (not 0), overwrite is explicit | Editing an existing month shows current numbers instead of zeros | B3 |
| BC3 | Rate 0/null treated as 1 in FBN aggregation (CLI + web), with a warning | If any stored row has rate=0, CLI totals will *increase* (those rows currently vanish); web already behaves this way | B4 |
| BC4 | Web position MTM / MTM % / total MTM become stock-only, matching the CLI | `/ibkr`, `/ibkr/pnl`, `/ibkr/mtm` numbers change wherever options are held | B1 |
| BC5 | `-p/--password` flag removed; `t.sh` deleted; `TT_PASSWORD` env var supported | Your launch script changes; **password should be rotated** | S1 |
| BC6 | Flex import no longer prints the token-bearing URL | One less output line during import | S3 |
| BC7 | Next.js 16.1.4 → 16.2.x + `npm audit fix` | Framework patch; no intended UI change | S4 |
| BC8 | HTTP timeouts (30 s) on Flex requests | Previously-hanging imports now fail with an error after 30 s | S7 |
| BC9 | `quote_refresh.py` and `migrate_to_supabase.py` deleted | Those entry points stop existing (owner confirmed unused) | D3, D4 |
| BC10 | DB-layer errors surfaced as errors instead of "0 rows" | Outages become visible instead of silent empties | B6 |
| BC11 | *(Optional — recommend but not required)* CLI switches from service-role key to anon key + login session | RLS actually applies to the CLI; service-role key leaves the laptop | S5 |
| BC12 | *(Owner-run, optional)* `DROP TABLE market_price` via provided migration script | Legacy table removed from the live DB — **only when you run the script yourself** | D2 |

---

**STOP — awaiting approval.** Reply with approval for the plan plus accept/reject per
BC1–BC12 (e.g., "plan ok, all BCs except BC11"), and I will begin Phase 4 at Step 0.
