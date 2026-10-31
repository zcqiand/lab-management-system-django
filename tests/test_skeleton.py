"""骨架冒烟：settings / urls 可导入（依赖 .env.test 夹具，不触 DB）。

脚手架自带冒烟是 miniprogram 先例——L4 不留「no tests ran」模板红，
首个 REQ 进来后由真功能测试自然取代本文件（可删）。
"""

from __future__ import annotations

import importlib


def test_settings_imports() -> None:
    settings = importlib.import_module("config.settings")
    assert settings.ROOT_URLCONF == "config.urls"
    assert settings.DEBUG is False  # .env.test 夹具值：测试期关闭 DEBUG


def test_urls_imports() -> None:
    from django.urls import URLPattern, URLResolver

    urlpatterns = importlib.import_module("config.urls").urlpatterns
    assert isinstance(urlpatterns, list)
    assert all(isinstance(p, (URLPattern, URLResolver)) for p in urlpatterns)
