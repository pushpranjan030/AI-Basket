import os
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
    load_dotenv()          # .env file se values padhta hai
except ImportError:
    pass


def _db_uri():
    # Pura URL ek hi env me do, ya alag-alag parts me
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = os.environ.get("DB_USER", "root")
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "ai_basket")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"


class Config:
    # Production me SECRET_KEY zaroor .env me set karo
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # MySQL "server has gone away" error se bachata hai
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"  # HTTPS pe 1 karo
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
