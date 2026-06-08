-- Supabase Schema for TradeTools
-- Run this SQL in the Supabase SQL Editor to create the tables

-- ==============================================
-- TRADES TABLE (IBKR trades)
-- ==============================================
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    account_id TEXT,
    underlying_symbol TEXT,
    symbol TEXT,
    description TEXT,
    expiry TEXT,
    put_call TEXT,
    strike NUMERIC,
    date_time TIMESTAMPTZ,
    quantity NUMERIC,
    trade_price NUMERIC,
    multiplier NUMERIC,
    ib_commission NUMERIC,
    currency TEXT,
    notes TEXT,
    open_close_indicator TEXT,
    delta NUMERIC,
    und_price NUMERIC
);

-- ==============================================
-- MARKET_PRICE TABLE (legacy compatibility)
-- ==============================================
CREATE TABLE IF NOT EXISTS market_price (
    symbol TEXT PRIMARY KEY,
    price NUMERIC,
    date_time TIMESTAMPTZ
);

-- ==============================================
-- MARKET_QUOTES TABLE
-- ==============================================
CREATE TABLE IF NOT EXISTS market_quotes (
    contract_key TEXT PRIMARY KEY,
    instrument_type TEXT NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT,
    underlying_symbol TEXT,
    expiry TEXT,
    put_call TEXT,
    strike NUMERIC,
    multiplier NUMERIC,
    conid TEXT,
    bid NUMERIC,
    ask NUMERIC,
    last NUMERIC,
    close NUMERIC,
    mark NUMERIC,
    status TEXT,
    quote_time TIMESTAMPTZ,
    raw_payload JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================
-- FBN TABLE (Account tracking)
-- ==============================================
CREATE TABLE IF NOT EXISTS fbn (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE,
    account TEXT,
    portfolio TEXT,
    investment NUMERIC,
    deposit NUMERIC,
    interest NUMERIC,
    dividend NUMERIC,
    distribution NUMERIC,
    tax NUMERIC,
    fee NUMERIC,
    other NUMERIC,
    cash NUMERIC,
    asset NUMERIC,
    currency TEXT,
    rate NUMERIC,
    UNIQUE(date, account)
);

-- ==============================================
-- EQUITY TABLE (Asset tracking)
-- ==============================================
CREATE TABLE IF NOT EXISTS equity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date DATE,
    description TEXT,
    account TEXT,
    category TEXT,
    currency TEXT,
    rate NUMERIC,
    balance NUMERIC,
    tax NUMERIC
);

-- ==============================================
-- BITCOIN TABLE (Bitcoin buys tracking)
-- ==============================================
CREATE TABLE IF NOT EXISTS bitcoin (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exchange TEXT NOT NULL,
    date DATE NOT NULL,
    date_on_chain DATE,
    quantity NUMERIC(16, 8) NOT NULL,
    cost_cad NUMERIC(14, 2) NOT NULL,
    account TEXT NOT NULL,
    fees_cad NUMERIC(12, 2),
    fees_sats BIGINT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================
-- ROW LEVEL SECURITY (RLS)
-- ==============================================

-- Enable RLS on all tables
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_price ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE fbn ENABLE ROW LEVEL SECURITY;
ALTER TABLE equity ENABLE ROW LEVEL SECURITY;
ALTER TABLE bitcoin ENABLE ROW LEVEL SECURITY;

-- Create policies for authenticated users
-- These allow full access for any authenticated user (single-user app)
CREATE POLICY "auth_all_trades" ON trades
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "auth_all_market_price" ON market_price
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "auth_all_market_quotes" ON market_quotes
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "auth_all_fbn" ON fbn
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "auth_all_equity" ON equity
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "auth_all_bitcoin" ON bitcoin
    FOR ALL USING (auth.role() = 'authenticated');

-- ==============================================
-- INDEXES (optional, for performance)
-- ==============================================
CREATE INDEX IF NOT EXISTS idx_trades_underlying_symbol ON trades(underlying_symbol);
CREATE INDEX IF NOT EXISTS idx_trades_date_time ON trades(date_time);
CREATE INDEX IF NOT EXISTS idx_market_quotes_symbol ON market_quotes(symbol);
CREATE INDEX IF NOT EXISTS idx_market_quotes_underlying_symbol ON market_quotes(underlying_symbol);
CREATE INDEX IF NOT EXISTS idx_market_quotes_quote_time ON market_quotes(quote_time);
CREATE INDEX IF NOT EXISTS idx_market_quotes_instrument_type ON market_quotes(instrument_type);
CREATE INDEX IF NOT EXISTS idx_fbn_date ON fbn(date);
CREATE INDEX IF NOT EXISTS idx_equity_date ON equity(date);
CREATE INDEX IF NOT EXISTS idx_bitcoin_date ON bitcoin(date);
CREATE INDEX IF NOT EXISTS idx_bitcoin_account ON bitcoin(account);
CREATE INDEX IF NOT EXISTS idx_bitcoin_exchange ON bitcoin(exchange);
