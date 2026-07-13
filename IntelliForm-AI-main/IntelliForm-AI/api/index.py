import sys
import os

# Add the 'backend' folder to the python path so local imports work correctly in Vercel
backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.append(backend_path)

from app import app

@app.route('/debug-vercel')
def debug_vercel():
    return {
        "status": "Flask is running on Vercel!",
        "sys.path": sys.path,
        "cwd": os.getcwd(),
        "routes": [str(rule) for rule in app.url_map.iter_rules()]
    }

