"""Bitcoin buys database operations using Supabase."""
import pandas as pd
from shared.supabase_client import get_client


def fetch_bitcoin_data() -> pd.DataFrame:
    """Fetch all bitcoin buys, sorted by date descending."""
    client = get_client()

    try:
        response = client.table('bitcoin').select('*').order('date', desc=True).execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as e:
        print(f"Error fetching bitcoin data: {e}")
        return pd.DataFrame()


def save_bitcoin_entry(entry_data: dict) -> bool:
    """Save a single bitcoin buy."""
    client = get_client()
    data = {k: v for k, v in entry_data.items() if k != 'id'}

    try:
        response = client.table('bitcoin').insert(data).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error saving bitcoin entry: {e}")
        return False


def update_bitcoin_entry(entry_id: int, entry_data: dict) -> bool:
    """Update an existing bitcoin buy by ID."""
    client = get_client()
    data = {k: v for k, v in entry_data.items() if k != 'id'}

    try:
        response = client.table('bitcoin').update(data).eq('id', entry_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error updating bitcoin entry: {e}")
        return False


def delete_bitcoin_entry(entry_id: int) -> bool:
    """Delete a single bitcoin buy by ID."""
    client = get_client()

    try:
        response = client.table('bitcoin').delete().eq('id', entry_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error deleting bitcoin entry: {e}")
        return False
