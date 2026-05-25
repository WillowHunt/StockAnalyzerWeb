import os
import time
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_NAME = os.getenv("DB_NAME", "stock_analyzer")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
STATIC_VERSION = str(int(time.time()))

DEFAULT_TICKER = "AAPL"
DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
