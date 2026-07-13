"""
MongoDB connection module.
Initializes a MongoClient and exposes the database + users collection.
"""

import time as _time
import certifi
from pymongo import MongoClient
from pymongo.errors import OperationFailure, ConnectionFailure, ServerSelectionTimeoutError
import config


def init_db():
    """Initialize MongoDB connection. Returns (db, users_collection)."""
    if not config.MONGO_URI:
        print("[WARN] MONGO_URI is not set! Falling back to local in-memory MongoDB via mongomock...")
        try:
            import mongomock
            client = mongomock.MongoClient()
            db = client["intelliform"]
            users_collection = db["users"]
            users_collection.create_index("email", unique=True)
            print("[OK] Initialized in-memory MongoDB via mongomock successfully!")
            return db, users_collection
        except Exception as mock_err:
            raise RuntimeError(f"Failed to initialize mongomock fallback: {mock_err}")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Connecting to MongoDB (attempt {attempt}/{max_retries})...")
            client = MongoClient(
                config.MONGO_URI,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=30000,
                socketTimeoutMS=30000,
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

        except Exception as e:
            if attempt < max_retries:
                print(f"  [WARN] Attempt {attempt} failed, retrying in 3s... Error: {e}")
                _time.sleep(3)
            else:
                print(f"\n[WARN] Connection to MongoDB failed: {e}")
                print("Falling back to local in-memory MongoDB using mongomock...")
                try:
                    import mongomock
                    client = mongomock.MongoClient()
                    db = client["intelliform"]
                    users_collection = db["users"]
                    users_collection.create_index("email", unique=True)
                    print("[OK] Initialized in-memory MongoDB via mongomock successfully!")
                    return db, users_collection
                except Exception as mock_err:
                    raise SystemExit(
                        f"\n[ERROR] Cannot connect to MongoDB and mongomock fallback failed!\n"
                        f"   Original MongoDB error: {e}\n"
                        f"   Mongomock error: {mock_err}\n"
                    )


# These will be set when init_db() is called from app.py
db = None
users_collection = None
