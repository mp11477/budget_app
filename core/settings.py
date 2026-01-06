from pathlib import Path
import subprocess, os

BASE_DIR = Path(__file__).resolve().parent.parent

'''Calendar variables'''
LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/calendar/"
KIOSK_CALENDAR_OWNER_USERNAME = "mike"  # <-- put your actual username
KIOSK_PIN = "1234"  # change this
KIOSK_UNLOCK_HOURS = 1
'''End of Calendar'''

'''Weather API variables'''
OPENWEATHER_API_KEY = "8701c16d491aaae7f8b3093b6770d835" # OpenWeatherMap API Key
LAT = '40.4467'       # Current LAT for home location
LON = '-79.8538'    # Current LONG for home location
'''End of Weather API'''

def current_git_branch():
    try:
        # Ensure we run git in the project directory
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=BASE_DIR,
        ).strip().decode()
        print(f"[settings.py] Detected git branch: {branch}")
        return branch
    except Exception as e:
        # Make it noisy if this fails so we know why it's defaulting
        print(f"[settings.py] Could not determine git branch, defaulting to 'main'. Error: {e!r}")
        return "main"

branch = current_git_branch()
print(f"[settings.py] BASE_DIR = {BASE_DIR}")

if branch == "main":
    db_file = BASE_DIR / "db.sqlite3"
else:
    db_file = BASE_DIR / "dev.sqlite3"

print(f"[settings.py] Using database file: {db_file}")

# Check the database in the shell just to be sure using these commands
# python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
# python manage.py showmigrations [app_label] (ex:  python manage.py showmigrations jobtracker)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': db_file,
    }
}

SECRET_KEY = 'django-insecure-local-dev'
DEBUG = True
ALLOWED_HOSTS = ['*']  # TEMPORARILY allows all
# For production, specify trusted IPs:
# ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.1.50']

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "budget-app-cache",
        "TIMEOUT": None,  # per-key timeouts will be used
    }
}

INSTALLED_APPS = [
    'budget.apps.BudgetConfig',
    "jobtracker.apps.JobtrackerConfig",
    "calendar_app.apps.CalendarAppConfig",
    'gigs.apps.GigsConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'budget.context_processors.kiosk_flag',
                
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'  # Keep this simple

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'), # Look in the top-level 'static' folder
]

# In production, collect all static files here:
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

#Set pin and kiosk settings
KIOSK_PINS = {
    "mike": "4075",
    "wife": "1982",
}

KIOSK_PIN_LABELS = {
    "mike": "Mike",
    "wife": "Stef",
}

KIOSK_UNLOCK_MINUTES = 5  # unlock duration in minutes



''' Directory structure:
#this is the PROJECT directory tree for budget_app
budget_app/
└── core/
    ├── settings.py
    ├── urls.py
    ├── wsgi.py

#This is the APPLICATION directory tree for budget
budget_app/
└── budget/
    ├── models.py
    ├── views.py
    ├── forms.py
    ├── admin.py
    ├── management/
    └── ...

'''