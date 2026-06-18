# Configuration loaded from environment variables
import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # Service role key for backend/CLI
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")  # Anon key for frontend

# IBKR Flex Query Configuration
IBKR_TOKEN = os.getenv("IBKR_TOKEN", "")
QUERY_ID_DAILY = os.getenv("QUERY_ID_DAILY", "")
QUERY_ID_WEEKLY = os.getenv("QUERY_ID_WEEKLY", "")
QUERY_ID_NAV = os.getenv("QUERY_ID_NAV", "")

# IB Gateway API Configuration
IB_GATEWAY_HOST = os.getenv("IB_GATEWAY_HOST", "127.0.0.1")
IB_GATEWAY_PORT = int(os.getenv("IB_GATEWAY_PORT", "7497"))
IB_GATEWAY_CLIENT_ID = int(os.getenv("IB_GATEWAY_CLIENT_ID", "1919"))
IB_GATEWAY_TIMEOUT = float(os.getenv("IB_GATEWAY_TIMEOUT", "5"))
IB_GATEWAY_READ_ONLY = os.getenv("IB_GATEWAY_READ_ONLY", "true").lower() in {"1", "true", "yes", "on"}
