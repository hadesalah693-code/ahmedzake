import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production-wisam-2026")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
PORT = int(os.environ.get("PORT", 5000))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
