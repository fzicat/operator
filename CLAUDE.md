# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Applications

**CLI App:**
```bash
python ./cli/main.py
```

**Web App:**
```bash
cd web
npm install
npm run dev
```

The web app runs at `http://localhost:3000`.

## Dependencies

**CLI Dependencies:**
```bash
pip install -r .\cli\requirements.txt
```
Required packages: `rich`, `pandas`, `requests`, `yahooquery`, `supabase`

**Web Dependencies:**
```bash
cd web
npm install
```
Key packages: `next`, `react`, `@supabase/supabase-js`, `tailwindcss`

## Environment Variables

The web app requires these environment variables in `web/.env.local`:
```
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
IBKR_TOKEN=your_ibkr_flex_token
QUERY_ID_DAILY=your_ibkr_query_id
```

## Architecture

TradeTools is a trading portfolio management application with two interfaces:
- **CLI**: Terminal-based application built with Rich for UI rendering
- **Web**: Next.js 14+ application with React and Tailwind CSS

Both share the same Supabase database.

## CLI Architecture

### Core Components

**Main Application (`main.py`)**
- `TradeToolsApp`: Main application class with Rich Console and Layout
- Uses Gruvbox color theme throughout
- Main loop: render layout -> get prompt -> process command
- `skip_render` flag allows modules to bypass layout rendering for large outputs

**Module System**
- `base_module.py`: Abstract `Module` class defining the interface
  - `handle_command(command)`: Process user input
  - `get_output()`: Return content for the body panel
  - `get_prompt()`: Return the command prompt string
- Modules switch via `app.switch_module(ModuleInstance)`
- Circular imports avoided by local imports in command handlers

**Available Modules**
- `HomeModule`: Main menu, routes to other modules (i, f, e, b commands)
- `IBKRModule`: Interactive Brokers trade management
- `FBNModule`: FBN account tracking (monthly/yearly stats)
- `EquityModule`: Personal equity/asset tracking
- `BitcoinModule`: Bitcoin buys tracking (add/edit/delete, list, stats report)

### Database Layer

### IBKR Module Specifics

- Imports trades via IBKR Flex Query API (XML parsing)
- FIFO-based PnL calculation in `calculate_pnl()`
- Tracks positions for stocks and options (putCall field: C/P or empty)
- MTM (Mark-to-Market) via yahooquery for current prices
- `target_percent` dict defines portfolio allocation targets

### UI Patterns

- Long output: Use `self.app.console.print()` directly and set `self.app.skip_render = True`
- Short output: Set `self.output_content` (string or Rich renderable like Table)
- Navigation: `q` returns to parent module, `qq` exits application

## Web Architecture

### Tech Stack
- **Framework**: Next.js 14+ (App Router)
- **UI**: React, Tailwind CSS with custom Gruvbox dark theme
- **Database**: Supabase (shared tables with CLI)
- **Auth**: Supabase Auth (email/password)

### Project Structure

```
web/
├── src/
│   ├── app/
│   │   ├── layout.tsx              # Root layout
│   │   ├── page.tsx                # Redirect to login or ibkr
│   │   ├── login/page.tsx          # Login page
│   │   ├── (authenticated)/        # Protected routes
│   │   │   ├── layout.tsx          # Nav, ErrorBanner, KeyboardHelp
│   │   │   ├── ibkr/               # IBKR module pages
│   │   │   ├── fbn/                # FBN module pages
│   │   │   └── equity/             # Equity module pages
│   │   └── api/
│   │       └── ibkr/
│   │           ├── import/route.ts # Flex Query import API
│   │           └── mtm/route.ts    # Yahoo Finance MTM API
│   ├── components/
│   │   ├── ui/                     # Button, Input, Table, Spinner, Select
│   │   └── layout/                 # Nav, ErrorBanner, KeyboardHelp
│   ├── lib/
│   │   ├── supabase.ts             # Supabase client with column mapping
│   │   ├── auth.tsx                # Auth context provider
│   │   ├── error-context.tsx       # Error state context
│   │   ├── hooks/useKeyboard.ts    # Keyboard navigation hook
│   │   └── utils/
│   │       ├── fifo.ts             # FIFO PnL calculation
│   │       └── format.ts           # Number/date formatting
│   └── types/index.ts              # TypeScript types and constants
```

### Key Patterns

**Supabase Client (`lib/supabase.ts`)**
- Lazy initialization to avoid build-time errors
- Column mapping between PostgreSQL snake_case and JavaScript camelCase
- `toCamelCase()`, `toSnakeCase()`, `toCamelCaseArray()` helpers

**FIFO Calculation (`lib/utils/fifo.ts`)**
- `calculatePnL()`: Computes realized P&L using FIFO matching
- `calculateCredit()`: Computes cumulative credit per symbol
- `calculatePositions()`: Aggregates trades into position summary
- `applyMtmPrices()`: Applies market prices for unrealized P&L

**Authentication (`lib/auth.tsx`)**
- React Context with user state and loading state
- Auto-refresh token on mount
- Session persistence via Supabase

**Keyboard Navigation (`lib/hooks/useKeyboard.ts`)**
- Global shortcuts: `?` help, `Esc` close, `1/2/3` module switch, `q` back
- Route-specific bindings passed via hook parameter
- Help overlay shows all available shortcuts

### Routes

| Route | Description |
|-------|-------------|
| `/login` | Email/password login |
| `/ibkr` | Positions summary with import/MTM buttons |
| `/ibkr/positions/[symbol]` | Position detail for a symbol |
| `/ibkr/trades` | All trades list |
| `/ibkr/stats/daily` | Daily P&L stats |
| `/ibkr/stats/weekly` | Weekly P&L stats |
| `/fbn` | Monthly stats summary |
| `/fbn/yearly` | Yearly stats |
| `/fbn/entry` | Add/edit FBN entry |
| `/fbn/assets/monthly` | Monthly assets matrix |
| `/fbn/assets/yearly` | Yearly assets matrix |
| `/equity` | Equity entries list |
| `/equity/entry` | Add/edit equity entry |
| `/equity/pivot` | Pivot tables view |
| `/bitcoin` | Bitcoin buys list (read-only) with summary |
| `/bitcoin/stats` | Bitcoin stats (totals, average cost, by account/exchange/year) |

### API Routes

**POST `/api/ibkr/import`**
- Fetches trades from IBKR Flex Query API
- Parses XML response and extracts trade attributes
- Upserts trades to Supabase (skips duplicates via `trade_id` conflict)

**POST `/api/ibkr/mtm`**
- Fetches current prices from Yahoo Finance v7 API
- Updates `market_price` table with current prices
- Only updates non-option symbols

### Theme (Gruvbox Dark)

CSS custom properties defined in `globals.css`:
- `--gruvbox-bg`: #282828 (background)
- `--gruvbox-fg`: #ebdbb2 (foreground)
- `--gruvbox-orange`: #fe8019 (accent)
- `--gruvbox-red`: #fb4934, `--gruvbox-green`: #b8bb26
- `--gruvbox-yellow`: #fabd2f, `--gruvbox-blue`: #83a598
- `--gruvbox-purple`: #d3869b, `--gruvbox-aqua`: #8ec07c

## Configuration

**CLI Configuration** (`shared/config.py`):
- Supabase credentials (URL and key)
- IBKR Flex Query credentials (token and query IDs)

**Web Configuration** (`web/.env.local`):
- `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `IBKR_TOKEN` and `QUERY_ID_DAILY` for trade import
