-- Migration: add Bitcoin module table
-- Run this SQL in the Supabase SQL Editor.

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

-- Row Level Security: full access for any authenticated user (single-user app)
ALTER TABLE bitcoin ENABLE ROW LEVEL SECURITY;

CREATE POLICY "auth_all_bitcoin" ON bitcoin
    FOR ALL USING (auth.role() = 'authenticated');

-- Indexes
CREATE INDEX IF NOT EXISTS idx_bitcoin_date ON bitcoin(date);
CREATE INDEX IF NOT EXISTS idx_bitcoin_account ON bitcoin(account);
CREATE INDEX IF NOT EXISTS idx_bitcoin_exchange ON bitcoin(exchange);

-- ==============================================
-- SEED DATA (import existing buys from bitcoin.csv)
-- Derived columns (sats, buy price) are computed by the apps, not stored.
-- ==============================================
INSERT INTO bitcoin (exchange, date, date_on_chain, quantity, cost_cad, account, fees_cad, fees_sats, notes) VALUES
  ('Crypto.com', '2021-08-30', NULL, 0.03822709, 4879.21, 'FZ', NULL, NULL, '(swap other crypto)'),
  ('Crypto.com', '2021-12-06', NULL, 0.01500000, 956.80, 'FZ', NULL, NULL, NULL),
  ('Crypto.com', '2021-12-13', NULL, 0.01500000, 950.41, 'FZ', NULL, NULL, NULL),
  ('Crypto.com', '2022-01-12', NULL, 0.02000000, 1119.09, 'FZ', NULL, NULL, NULL),
  ('Crypto.com', '2022-04-18', NULL, 0.02000000, 1017.21, 'FZ', NULL, NULL, NULL),
  ('Crypto.com', '2022-05-10', NULL, 0.02500000, 1056.87, 'FZ', NULL, NULL, NULL),
  ('Crypto.com', '2022-06-13', NULL, 0.05000000, 1557.05, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2025-08-11', NULL, 0.00607210, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2025-08-14', NULL, 0.01190000, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2025-08-15', NULL, 0.01200000, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Bitcoin Well', '2025-08-27', NULL, 0.00015917, 25.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2025-08-28', NULL, 0.03152048, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Bitcoin Well', '2025-08-29', NULL, 0.00627894, 950.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-09-08', NULL, 0.01260810, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-09-10', NULL, 0.03095189, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-09-17', NULL, 0.00610060, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Bitcoin Well', '2025-09-17', NULL, 0.00619721, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2025-09-17', NULL, 0.00611114, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-09-22', NULL, 0.03142349, 5000.00, 'MPM', NULL, NULL, NULL),
  ('Bitcoin Well', '2025-09-22', NULL, 0.03166165, 5000.00, 'MPM', NULL, NULL, NULL),
  ('Coinbase', '2025-09-22', NULL, 0.03135663, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-09-25', NULL, 0.06309878, 10000.00, 'MPM', NULL, 800, NULL),
  ('Bitcoin Well', '2025-09-27', NULL, 0.05797085, 9000.00, 'MPM', NULL, 185, NULL),
  ('Bull Bitcoin', '2025-09-29', NULL, 0.06155894, 10000.00, 'MPM', NULL, 115, NULL),
  ('Bitcoin Well', '2025-09-29', NULL, 0.05306004, 9000.00, 'MPM', NULL, 300, NULL),
  ('Bull Bitcoin', '2025-09-29', NULL, 0.05817399, 10000.00, 'MPM', NULL, 300, NULL),
  ('Bitcoin Well', '2025-10-03', NULL, 0.05267819, 9000.00, 'MPM', NULL, 250, NULL),
  ('Bull Bitcoin', '2025-10-07', NULL, 0.04054092, 7000.00, 'MPM', NULL, 250, NULL),
  ('Bitcoin Well', '2025-10-10', NULL, 0.05382106, 9000.00, 'MPM', NULL, 200, NULL),
  ('Bitcoin Well', '2025-10-11', NULL, 0.00644981, 1000.00, 'GFZ', NULL, 100, 'move to GFZ 25-10-22'),
  ('Bitcoin Well', '2025-10-11', NULL, 0.05159850, 8000.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-10-16', NULL, 0.03207862, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Bull Bitcoin', '2025-10-17', NULL, 0.03291403, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Bitcoin Well', '2025-10-21', NULL, 0.05593651, 9000.00, 'GFZ', NULL, 100, 'move to GFZ 25-10-22'),
  ('Bitcoin Well', '2025-10-22', '2025-10-28', 0.00060976, 100.00, 'GFZ', NULL, 150, 'move to GFZ 25-10-31'),
  ('Bitcoin Well', '2025-10-28', '2025-10-30', 0.06502885, 9900.00, 'GFZ', NULL, 150, 'move to GFZ 25-10-31'),
  ('Bitcoin Well', '2025-10-31', '2025-11-04', 0.06854276, 9900.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-12'),
  ('Bitcoin Well', '2025-11-04', '2025-11-06', 0.06853477, 9900.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-12'),
  ('Bitcoin Well', '2025-11-06', '2025-11-10', 0.06596956, 9910.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-12'),
  ('Bitcoin Well', '2025-11-10', '2025-11-13', 0.07089207, 9920.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-23'),
  ('Bitcoin Well', '2025-11-12', '2025-11-15', 0.07335908, 9930.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-23'),
  ('Bitcoin Well', '2025-11-14', '2025-11-18', 0.07500242, 9940.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-23'),
  ('Bitcoin Well', '2025-11-18', '2025-11-20', 0.08023069, 9950.00, 'GFZ', NULL, 200, 'move to GFZ 25-11-23'),
  ('Bitcoin Well', '2025-11-20', '2025-11-24', 0.07908353, 9960.00, 'GFZ', NULL, 300, 'move to GFZ 25-11-25'),
  ('Bitcoin Well', '2025-12-30', '2025-12-30', 0.40535498, 50000.00, 'GFZ', NULL, 800, 'move to GFZ 25-12-30'),
  ('Coinbase', '2026-05-01', NULL, 0.04586116, 5000.00, 'FZ', 73.41, NULL, NULL),
  ('Coinbase', '2026-05-05', NULL, 0.04470388, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-06', NULL, 0.01777243, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-07', NULL, 0.01795919, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-08', NULL, 0.00905225, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-08', NULL, 0.00890885, 1000.00, 'FZ', 14.68, NULL, NULL),
  ('Coinbase', '2026-05-09', NULL, 0.00883163, 1000.00, 'FZ', 14.68, NULL, NULL),
  ('Coinbase', '2026-05-10', NULL, 0.00875861, 1000.00, 'FZ', 14.68, NULL, NULL),
  ('Coinbase', '2026-05-11', NULL, 0.04420503, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-12', NULL, 0.01805593, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-13', NULL, 0.04567268, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-14', NULL, 0.01767394, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-15', NULL, 0.04601721, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-17', NULL, 0.01844599, 2000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-18', NULL, 0.04711377, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-19', NULL, 0.04689445, 5000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-20', NULL, 0.02326695, 2500.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-21', NULL, 0.00926475, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-22', NULL, 0.00933350, 1000.00, 'FZ', NULL, NULL, NULL),
  ('Coinbase', '2026-05-23', NULL, 0.00937694, 1000.00, 'FZ', NULL, NULL, NULL);
