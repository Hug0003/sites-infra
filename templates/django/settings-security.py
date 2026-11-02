
# --- Production (Docker) : tout ce qui est sensible vient de l'environnement ---
# Valeurs par défaut sûres : sans DJANGO_DEBUG=1, l'appli tourne en mode production.

# Préfixe d'URL quand le site est servi sous hugomeuriel.fr/projets/<nom>/.
SCRIPT_NAME = os.environ.get("DJANGO_SCRIPT_NAME", "").rstrip("/")
if SCRIPT_NAME:
    FORCE_SCRIPT_NAME = SCRIPT_NAME
STATIC_URL = f"{SCRIPT_NAME}/static/"
MEDIA_URL = f"{SCRIPT_NAME}/media/"

DATABASES["default"]["NAME"] = os.environ.get("DJANGO_DB_PATH", BASE_DIR / "db.sqlite3")
STATIC_ROOT = os.environ.get("DJANGO_STATIC_ROOT", os.path.join(BASE_DIR, "static"))
MEDIA_ROOT = os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media")

LOGIN_URL = "login"

# Taille maximale des formulaires et des images envoyés : 5 Mo.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

if not DEBUG:
    # Le HTTPS s'arrête sur l'Apache de 192.168.11.131, qui transmet X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    # HSTS limité à hugomeuriel.fr : photos.hugomeuriel.fr (Raspberry) est géré à part,
    # et l'inscription « preload » dans les navigateurs est quasi irréversible.
    SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if "." in h]
    # Cookies limités à l'appli : les autres projets du domaine ne les reçoivent pas.
    SESSION_COOKIE_PATH = SCRIPT_NAME or "/"
    CSRF_COOKIE_PATH = SCRIPT_NAME or "/"
    SESSION_COOKIE_SAMESITE = "Lax"
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Erreurs visibles dans « docker compose logs » (sinon Django les envoie par e-mail aux ADMINS).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
