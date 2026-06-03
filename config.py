"""Configuration loaded from environment variables (.env file)."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API keys ---
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# --- Email (SMTP) ---
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")  # Gmail App Password
EMAIL_TO = os.getenv("EMAIL_TO", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# --- Analysis parameters ---
LOOKBACK_DAYS = 90          # ~3 months of trading data
MIN_PRICE = 5.00            # filter out penny stocks
MIN_AVG_VOLUME = 100_000    # filter illiquid names
IPO_LOOKAHEAD_DAYS = 7      # upcoming IPOs to flag

# --- Scheduling ---
RUN_TIME = os.getenv("RUN_TIME", "07:00")   # 7:00 AM local time
TIMEZONE = os.getenv("TIMEZONE", "US/Eastern")

# --- Output ---
SAVE_CSV = os.getenv("SAVE_CSV", "true").lower() == "true"
CSV_DIR = os.getenv("CSV_DIR", "./reports")
