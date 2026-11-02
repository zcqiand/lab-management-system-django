"""Django settings —— 实验室管理 Django 版（lab-management-system-django）。

fail-fast 纪律（suite-hard-rules §1）：环境变量缺失即崩，禁止默认值兜底。
dev/test 由仓根 .env.local / .env.test 注入（三件套 key 集合走 L0.5 一致性门），
prod 由 deploy env-file 注入。家族 PG 三库接线在首个 REQ 落位时定型。
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent  # src/


def _env(key: str) -> str:
    """读必需环境变量；缺失/空值即崩（suite-hard-rules §1，无兜底）。"""
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"缺少必需环境变量 {key}（suite-hard-rules §1 禁止默认值兜底）")
    return value


SECRET_KEY = _env("DJANGO_SECRET_KEY")
DEBUG = _env("DJANGO_DEBUG") == "true"
ALLOWED_HOSTS = [h.strip() for h in _env("DJANGO_ALLOWED_HOSTS").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "contracts",
    "entities",
    "authn",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# 家族 PG 三库（dev/test=本机 127.0.0.1:54321）：DATABASE_URL 单串注入，
# 与家族各后端同形。django 只是消费方，库名归家族档案（docs/families/*.md）管。
DATABASES = {
    "default": dj_database_url.parse(_env("DATABASE_URL"), conn_max_age=0),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "lab_management_system_django.auth.BearerAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "lab_management_system_django.errors.envelope_exception_handler",
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
