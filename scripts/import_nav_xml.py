"""
One-time import of a NAV Flex Query XML file into the Supabase `nav` table.

Use this to backfill the full history from a manually-downloaded report
(e.g. ~/NAV.xml) without having IBKR regenerate the statement. Afterwards you
can switch the live Flex Query to a short (1-2 week) window and use the
`i n` / `import nav` command for daily incremental imports.

Usage:
    python scripts/import_nav_xml.py                # reads ~/NAV.xml
    python scripts/import_nav_xml.py /path/to/NAV.xml

The insert is duplicate-safe: rows are upserted on `date` with
ignore_duplicates, so existing days are never overwritten and re-running is a
no-op. Make sure the `nav` table exists (scripts/migrations/20260617_add_nav.sql)
and your .env has SUPABASE_URL / SUPABASE_KEY set.
"""
import os
import sys
import xml.etree.ElementTree as ET

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.db import nav_db


def _safe_float(elem, key):
    val = elem.get(key)
    if val is None or not str(val).strip():
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _localname(elem):
    """Tag without any namespace prefix."""
    return elem.tag.rsplit('}', 1)[-1]


def parse_nav_xml(xml_content: bytes) -> list[dict]:
    """Parse NAV Flex Query XML into one row per day (last equity summary +
    deposits/withdrawals), matching the CLI's process_nav_xml logic."""
    root = ET.fromstring(xml_content)

    rows = {}
    for eq in root.iter():
        if _localname(eq) != 'EquitySummaryInBase':
            continue
        items = [c for c in eq.iter() if _localname(c) == 'EquitySummaryByReportDateInBase']
        if not items:
            continue
        last = items[-1]
        report_date = last.get('reportDate')
        if not report_date:
            continue
        rows[report_date] = {
            'date': report_date,
            'cash': _safe_float(last, 'cash'),
            'stock': _safe_float(last, 'stock'),
            'options': _safe_float(last, 'options'),
            'dividend_accruals': _safe_float(last, 'dividendAccruals'),
            'interest_accruals': _safe_float(last, 'interestAccruals'),
            'total': _safe_float(last, 'total'),
            'deposits_withdrawals': None,
        }

    for chg in root.iter():
        if _localname(chg) != 'ChangeInNAV':
            continue
        to_date = chg.get('toDate')
        if not to_date:
            continue
        deposits = _safe_float(chg, 'depositsWithdrawals')
        if to_date in rows:
            rows[to_date]['deposits_withdrawals'] = deposits
        else:
            rows[to_date] = {
                'date': to_date,
                'cash': None,
                'stock': None,
                'options': None,
                'dividend_accruals': None,
                'interest_accruals': None,
                'total': None,
                'deposits_withdrawals': deposits,
            }

    return [rows[d] for d in sorted(rows)]


def main():
    default_path = os.path.expanduser('~/NAV.xml')
    path = sys.argv[1] if len(sys.argv) > 1 else default_path

    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Reading {path} ...")
    with open(path, 'rb') as f:
        xml_content = f.read()

    rows = parse_nav_xml(xml_content)
    if not rows:
        print("No NAV data found in the file. Nothing to import.")
        sys.exit(1)

    print(f"Parsed {len(rows)} day(s): {rows[0]['date']} -> {rows[-1]['date']}")
    print("Inserting (duplicate-safe) ...")
    count_new = nav_db.save_nav_rows(rows)
    print(f"Done. {count_new} new day(s) inserted "
          f"({len(rows) - count_new} already existed / skipped).")


if __name__ == '__main__':
    main()
