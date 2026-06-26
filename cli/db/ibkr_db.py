"""IBKR database operations using Supabase."""
import pandas as pd
from datetime import datetime
from shared.supabase_client import get_client

# Column mapping from SQLite camelCase to PostgreSQL snake_case
COLUMN_MAP = {
    'tradeID': 'trade_id',
    'accountId': 'account_id',
    'underlyingSymbol': 'underlying_symbol',
    'symbol': 'symbol',
    'description': 'description',
    'expiry': 'expiry',
    'putCall': 'put_call',
    'strike': 'strike',
    'dateTime': 'date_time',
    'quantity': 'quantity',
    'tradePrice': 'trade_price',
    'multiplier': 'multiplier',
    'ibCommission': 'ib_commission',
    'currency': 'currency',
    'notes': 'notes',
    'openCloseIndicator': 'open_close_indicator',
    'delta': 'delta',
    'und_price': 'und_price',
}

# Reverse mapping for reading data back
REVERSE_COLUMN_MAP = {v: k for k, v in COLUMN_MAP.items()}


def _convert_datetime(dt_str):
    """Convert compact datetime string (YYYYMMDDHHmmss) to ISO format for PostgreSQL."""
    if not dt_str:
        return None
    if isinstance(dt_str, str) and len(dt_str) == 14 and dt_str.isdigit():
        try:
            dt = datetime.strptime(dt_str, '%Y%m%d%H%M%S')
            return dt.isoformat()
        except ValueError:
            return dt_str
    return dt_str


def _to_snake_case(data: dict) -> dict:
    """Convert camelCase keys to snake_case and convert datetime fields."""
    result = {}
    for k, v in data.items():
        new_key = COLUMN_MAP.get(k, k)
        # Convert datetime fields from compact format to ISO
        if new_key == 'date_time':
            v = _convert_datetime(v)
        result[new_key] = v
    return result


def _to_camel_case(data: dict) -> dict:
    """Convert snake_case keys back to camelCase."""
    return {REVERSE_COLUMN_MAP.get(k, k): v for k, v in data.items()}


def save_trade(trade_data: dict) -> bool:
    """
    Saves a trade dictionary to the database.
    Ignores if trade_id already exists.
    """
    client = get_client()
    data = _to_snake_case(trade_data)

    try:
        # Use upsert with onConflict to handle existing records
        response = client.table('trades').upsert(
            data,
            on_conflict='trade_id',
            ignore_duplicates=True
        ).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error saving trade {trade_data.get('tradeID')}: {e}")
        return False


def update_trade_fields(trade_id: str, updates: dict) -> bool:
    """
    Updates specific fields for a trade.
    updates: dict of column_name -> value (camelCase keys accepted)
    """
    client = get_client()
    data = _to_snake_case(updates)

    try:
        response = client.table('trades').update(data).eq('trade_id', trade_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error updating trade {trade_id}: {e}")
        return False


def fetch_all_trades_as_df() -> pd.DataFrame:
    """
    Retrieves all trades from the database ordered by date_time.
    Returns a pandas DataFrame with camelCase column names for compatibility.
    """
    client = get_client()

    try:
        response = client.table('trades').select('*').order('date_time').execute()
        if not response.data:
            return pd.DataFrame()

        df = pd.DataFrame(response.data)
        # Convert column names back to camelCase for compatibility with existing code
        df.columns = [REVERSE_COLUMN_MAP.get(col, col) for col in df.columns]
        return df
    except Exception as e:
        print(f"Error fetching all trades: {e}")
        return pd.DataFrame()


def save_market_price(symbol: str, price: float, date_time: str) -> bool:
    """
    Saves a market price to the database.
    Uses upsert to handle updates efficiently.
    """
    client = get_client()

    try:
        response = client.table('market_price').upsert({
            'symbol': symbol,
            'price': price,
            'date_time': _convert_datetime(date_time)
        }, on_conflict='symbol').execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error saving market price for {symbol}: {e}")
        return False


def fetch_latest_market_prices() -> dict:
    """
    Retrieves the latest market price for each symbol.
    Returns a dictionary {symbol: price}
    """
    client = get_client()

    try:
        response = client.table('market_price').select('symbol, price').execute()
        return {row['symbol']: row['price'] for row in response.data}
    except Exception as e:
        print(f"Error fetching market prices: {e}")
        return {}


def fetch_symbol_targets() -> dict:
    """
    Retrieves all symbol targets from the database.
    Returns a dictionary {symbol: target_percent}
    """
    client = get_client()

    try:
        response = client.table('symbol_targets').select('symbol, target_percent').execute()
        return {row['symbol']: float(row['target_percent']) for row in response.data}
    except Exception as e:
        print(f"Error fetching symbol targets: {e}")
        return {}


def fetch_symbol_baskets() -> dict:
    """
    Retrieves all symbol baskets from the database.
    Returns a dictionary {symbol: basket}
    """
    client = get_client()

    try:
        response = client.table('symbol_targets').select('symbol, basket').execute()
        return {row['symbol']: row.get('basket') for row in response.data}
    except Exception as e:
        print(f"Error fetching symbol baskets: {e}")
        return {}


def fetch_symbol_margin_requirements() -> dict:
    """
    Retrieves margin requirement multipliers (0-1) per symbol.
    Returns a dictionary {symbol: margin_requirements}
    """
    client = get_client()

    try:
        response = client.table('symbol_targets').select('symbol, margin_requirements').execute()
        return {
            row['symbol']: float(row['margin_requirements'])
            for row in response.data
            if row.get('margin_requirements') is not None
        }
    except Exception as e:
        print(f"Error fetching symbol margin requirements: {e}")
        return {}


def fetch_symbol_scores() -> dict:
    """
    Retrieves the integer score (typically 0-100) per symbol.
    Returns a dictionary {symbol: score}
    """
    client = get_client()

    try:
        response = client.table('symbol_targets').select('symbol, score').execute()
        return {
            row['symbol']: int(row['score'])
            for row in response.data
            if row.get('score') is not None
        }
    except Exception as e:
        print(f"Error fetching symbol scores: {e}")
        return {}
