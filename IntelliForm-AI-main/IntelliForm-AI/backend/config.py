import os
from dotenv import load_dotenv

# Load .env from project root (one level above backend/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

BASE_DIR = os.path.dirname(__file__)

# Flask config
SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback_secret')
DEBUG = os.environ.get('FLASK_ENV') == 'development'

# Template and static folders (relative to backend/)
TEMPLATE_FOLDER = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'templates'))
STATIC_FOLDER = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'static'))

# MongoDB
MONGO_URI = os.environ.get('MONGO_URI', '')

# JWT
JWT_SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback_jwt_secret')
JWT_TOKEN_EXPIRY_HOURS = 24

# Gemini AI
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
