"""
MongoDB connection module.
Initializes a MongoClient and exposes the database + users collection.
"""

import time as _time
import certifi
from pymongo import MongoClient
import os
import config
from pymongo.errors import OperationFailure, ConnectionFailure, ServerSelectionTimeoutError, InvalidURI, ConfigurationError


def init_db():
    """Initialize MongoDB connection. Returns (db, users_collection)."""
    # Detect Vercel / serverless environment
    is_vercel = 'VERCEL' in os.environ or 'AWS_LAMBDA_FUNCTION_NAME' in os.environ

    def get_mongomock_fallback(original_err=None):
        print(f"[WARN] Falling back to local in-memory MongoDB using mongomock... (Reason: {original_err})")
        try:
            import mongomock
            client = mongomock.MongoClient()
            db = client["intelliform"]
            users_collection = db["users"]
            users_collection.create_index("email", unique=True)
            print("[OK] Initialized in-memory MongoDB via mongomock successfully!")
            return db, users_collection
        except Exception as mock_err:
            if is_vercel:
                # On Vercel, don't crash the entire function, just return mock if possible
                raise RuntimeError(f"Cannot initialize mongomock fallback: {mock_err}")
            else:
                raise SystemExit(
                    f"\n[ERROR] Cannot connect to MongoDB and mongomock fallback failed!\n"
                    f"   Original MongoDB error: {original_err}\n"
                    f"   Mongomock error: {mock_err}\n"
                )

    if not config.MONGO_URI:
        return get_mongomock_fallback("MONGO_URI not set")

    # Fast timeout on Vercel/serverless to avoid hitting Vercel's 10s timeout limit
    timeout_ms = 3000 if is_vercel else 10000
    max_retries = 1 if is_vercel else 3

    for attempt in range(1, max_retries + 1):
        try:
            print(f"Connecting to MongoDB (attempt {attempt}/{max_retries})...")
            client = MongoClient(
                config.MONGO_URI,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
                socketTimeoutMS=timeout_ms,
                retryWrites=True,
            )

            # Force a connection test
            client.admin.command('ping')

            db = client.get_default_database("intelliform")
            users_collection = db["users"]

            # Create unique index on email to prevent duplicates
            users_collection.create_index("email", unique=True)

            print("[OK] Connected to MongoDB successfully!")
            return db, users_collection

        except InvalidURI as e:
            print(f"[ERROR] Invalid MongoDB URI syntax: {e}")
            return get_mongomock_fallback(e)
        except Exception as e:
            if attempt < max_retries:
                print(f"  [WARN] Attempt {attempt} failed, retrying in 3s... Error: {e}")
                _time.sleep(3)
            else:
                return get_mongomock_fallback(e)



# These will be set when init_db() is called from app.py
db = None
users_collection = None
