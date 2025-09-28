# migrate.py
# This script is designed to run once, create tables, and exit successfully.

from billing_app_1 import init_db
import sys

try:
    print("Running database initialization (init_db) via migrate.py...")
    init_db()
    print("Database schema created and products seeded successfully.")
    sys.exit(0)
except Exception as e:
    print(f"FATAL DATABASE INIT ERROR: {e}")
    sys.exit(1)