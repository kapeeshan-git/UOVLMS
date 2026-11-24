"""Django settings for University of Vavuniya LMS (MySQL 8.x + SPA frontend)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(BASE_DIR / ".env")
_load_dotenv(PROJECT_ROOT / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    value = os.environ.get(key)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    h.strip()
    for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
SITE_URL = env("SITE_URL", "http://localhost:5173").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.catalog",
    "apps.circulation",
    "apps.notifications",
    "apps.imports",
    "apps.demo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
APPEND_SLASH = False
TEMPLATES = []

# --- Database (MySQL 8.x default, sqlite fallback for quick isolated unit checks) ---
if env("DB_ENGINE", "mysql") == "sqlite":
    (BASE_DIR / "var").mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "var" / "dev.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME", "lms"),
            "USER": env("DB_USER", "lms"),
            "PASSWORD": env("DB_PASSWORD", "lms1234"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "3306"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "charset": "utf8mb4",
                "isolation_level": "read committed",
                "init_command": (
                    "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,"
                    "ERROR_FOR_DIVISION_BY_ZERO', innodb_ft_enable_stopword=OFF"
                ),
            },
            "TEST": {
                "NAME": "test_lms",
                "CHARSET": "utf8mb4",
                "COLLATION": "utf8mb4_0900_ai_ci",
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
]

# --- Time & language ---
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Colombo"
USE_I18N = False
USE_TZ = True

# --- Security & Single-Origin Cookie Config ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 10
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG and SITE_URL.startswith("https")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
CSRF_TRUSTED_ORIGINS = list(
    {
        SITE_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }
)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# --- Email ---
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "1025"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = BASE_DIR / "var" / "mail"
    EMAIL_FILE_PATH.mkdir(parents=True, exist_ok=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "library@vau.ac.lk")

FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# --- Library policy (guide 9.8) ---
LIBRARY_CLOSED_WEEKDAYS = [6]  # Sunday (Monday=0)
ENFORCE_ISSUE_HOURS = env_bool("ENFORCE_ISSUE_HOURS", False)
GRACE_MINUTES = int(env("GRACE_MINUTES", "0"))
COUNT_CLOSED_DAYS_IN_FINES = env_bool("COUNT_CLOSED_DAYS_IN_FINES", False)
BLOCK_ISSUE_IF_FINE_BALANCE_OVER = None
ACADEMIC_YEAR_START = (1, 1)
MAX_STUDENT_YEAR = 4
LARGE_WAIVER_LIMIT = 500  # LKR
DEMO_CLOCK_ENABLED = env_bool("DEMO_CLOCK_ENABLED", True)

# Background jobs
JOB_MAX_ATTEMPTS = 5
JOB_BACKOFF_SECONDS = 30
JOB_STALE_MINUTES = 10
