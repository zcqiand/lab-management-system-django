#!/usr/bin/env python
"""Django 管理入口 —— __PROJECT_CN__（__PROJECT__）。

用法：python manage.py runserver / migrate / test
settings 走 src/config/settings.py（fail-fast，环境变量先就位再跑）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    src_path = Path(__file__).resolve().parent / "src"
    sys.path.insert(0, str(src_path))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            '找不到 Django。依赖还没装：pip install -e ".[dev]"（装全局 python，见仓 CLAUDE.md）'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
