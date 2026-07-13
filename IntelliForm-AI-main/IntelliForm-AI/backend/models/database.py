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
        raise ValueError(
            "\n[ERROR] MONGO_URI is not set! Add it to your .env file.\n"
            "Example: MONGO_URI=mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/intelliform?retryWrites=true&w=majority\n"
        )

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

        except OperationFailure as e:
            raise SystemExit(
                "\n[ERROR] MongoDB Authentication Failed!\n"
                "   Your username or password in MONGO_URI is incorrect.\n"
                "   Fix your .env file:\n"
                "   MONGO_URI=mongodb+srv://USERNAME:PASSWORD@cluster0.xxxx.mongodb.net/intelliform\n"
                "\n   Tips:\n"
                "   - Make sure you replaced <db_password> with your ACTUAL password\n"
                "   - Remove any quotes around the URI\n"
                "   - If your password has special characters (@, #, !, etc.), use only letters & numbers instead\n"
                f"\n   Original error: {e}\n"
            )

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            if attempt < max_retries:
                print(f"  [WARN] Attempt {attempt} failed, retrying in 3s...")
                _time.sleep(3)
            else:
                raise SystemExit(
                    "\n[ERROR] Cannot connect to MongoDB!\n"
                    "   Check your internet connection and that your IP is whitelisted in MongoDB Atlas.\n"
                    "   Go to: MongoDB Atlas → Network Access → Add your current IP or 0.0.0.0/0\n"
                    f"\n   Original error: {e}\n"
                )


# These will be set when init_db() is called from app.py
db = None
users_collection = None
