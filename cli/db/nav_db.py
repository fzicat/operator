"""Net Asset Value (NAV) database operations using Supabase."""
import pandas as pd
from shared.supabase_client import get_client


def save_nav_rows(rows: list[dict]) -> int:
    """
    Insert NAV rows, one per day, skipping dates that already exist.

    Each row must contain a 'date' key (YYYY-MM-DD). Uses upsert with
    on_conflict='date' and ignore_duplicates so existing days are never
    overwritten and no duplicates are created.

    Returns the number of new rows inserted.
    """
    if not rows:
        return 0

    client = get_client()
    try:
        response = client.table('nav').upsert(
            rows,
            on_conflict='date',
            ignore_duplicates=True
        ).execute()
        return len(response.data)
    except Exception as e:
        print(f"Error saving NAV rows: {e}")
        return 0


def fetch_nav_as_df() -> pd.DataFrame:
    """Retrieve all NAV rows ordered by date as a DataFrame."""
    client = get_client()
    try:
        response = client.table('nav').select('*').order('date').execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as e:
        print(f"Error fetching NAV data: {e}")
        return pd.DataFrame()
