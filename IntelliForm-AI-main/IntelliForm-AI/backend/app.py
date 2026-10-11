# -*- coding: utf-8 -*-
"""
IntelliForm-AI -- Flask entry point
"""

# Fix Windows console encoding (cp1252 can't handle Unicode emoji)
import sys, io, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import logging
is_production_cloud = 'VERCEL' in os.environ or 'AWS_LAMBDA_FUNCTION_NAME' in os.environ or 'RENDER' in os.environ
handlers = [logging.StreamHandler(sys.stdout)]
if not is_production_cloud:
    handlers.append(logging.FileHandler('flask_debug.log', encoding='utf-8', mode='w'))

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)


import config

from flask import Flask
from models import database
from routes.auth import auth_bp
from routes.form import form_bp

app = Flask(
    __name__,
    template_folder=config.TEMPLATE_FOLDER,
    static_folder=config.STATIC_FOLDER,
)

app.secret_key = config.SECRET_KEY
app.debug      = config.DEBUG

db, users_col = database.init_db()
database.db = db
database.users_collection = users_col

app.register_blueprint(auth_bp)
app.register_blueprint(form_bp)

if __name__ == '__main__':
    logger.info("Starting IntelliForm-AI server...")
    app.run(debug=True)