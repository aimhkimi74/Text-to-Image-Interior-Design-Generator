import os
import logging
import requests
from urllib.parse import urlparse
from functools import wraps
import time
from dotenv import load_dotenv  # Add this to load .env file
from app import create_app, db
from flask_migrate import Migrate
from urllib.parse import urlparse


# Load environment variables from .env file if present
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level, logging.INFO))


def monitor_response_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"Operation '{func.__name__}' completed in {duration:.2f} seconds")
            return result
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(f"Operation '{func.__name__}' failed after {duration:.2f} seconds: {str(e)}")
            raise
    return wrapper

def validate_backend_url(url):
    try:
        parsed_url = urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            return False, "Invalid URL format"

        health_url = f"{url.rstrip('/')}/health"
        response = requests.get(health_url, timeout=5)

        if response.status_code == 200:
            logger.info("✅ Colab backend /health check passed")
            return True, "Backend is accessible"
        else:
            logger.error(f"Backend /health check failed with status code: {response.status_code}")
            return False, f"Backend not accessible (Status: {response.status_code})"
    except requests.Timeout:
        logger.error("Backend connection timed out")
        return False, "Backend connection timeout"
    except Exception as e:
        logger.error(f"Backend connection error: {str(e)}")
        return False, f"Error: {str(e)}"

# Initialize Flask app
app = create_app()

# Get backend URL from environment, no default fallback to force explicit setting
colab_url = os.getenv('COLAB_ENDPOINT', '').strip()

# Fail fast if no backend URL is set
if not colab_url:
    raise RuntimeError("COLAB_ENDPOINT environment variable must be set to your backend URL!")

# Set backend URL and timeout in app config
app.config['COLAB_ENDPOINT'] = colab_url
app.config['BACKEND_TIMEOUT'] = int(os.getenv('BACKEND_TIMEOUT', 60))

# Validate backend availability before starting
is_valid, message = validate_backend_url(colab_url)
app.config['BACKEND_AVAILABLE'] = is_valid

if is_valid:
    parsed = urlparse(colab_url)
    safe_host = f"{parsed.scheme}://{parsed.netloc}"
    logger.info(f"✅ Connected to Colab backend at {safe_host}")

else:
    logger.error(f"⚠️ Could not connect to Colab backend: {message}")
    if os.getenv("STRICT_BACKEND_CHECK", "false").lower() == "true":
        raise RuntimeError(f"Backend not accessible: {message}")
    logger.info("Application will start but image generation features may be unavailable")
    app.config['BACKEND_ERROR_MESSAGE'] = f"Backend connection failed: {message}"
    app.config['OFFLINE_MODE'] = True

if __name__ == '__main__':
    # Run Flask app on all network interfaces, debug off for production
    app.run(host='0.0.0.0', port=5000, use_reloader=False, debug=app.config.get('DEBUG', False))