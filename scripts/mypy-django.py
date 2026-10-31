#!/usr/bin/env python
"""L3 mypy 包装器：给 django-stubs 插件灌 .env.test 后再进 mypy。

django-stubs 的 mypy 插件启动时会真实 import DJANGO_SETTINGS_MODULE；本项目 settings
fail-fast（suite-hard-rules §1）无默认值兜底，所以类型检查前先把 `.env.test`
（已入库的测试夹具值，fastapi 仓先例）灌进 os.environ，再经 mypy.api 执行。
只影响静态检查进程，不改变运行时语义。gate L3 经 stack.json 调本脚本；
argv 透传给 mypy（如 `--strict src`）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _bootstrap_env_test() -> None:
    """把 .env.test 灌进 os.environ（已设键不覆盖——显式 env 优先）。"""
    env_file = ROOT / ".env.test"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    _bootstrap_env_test()
    from mypy import api

    stdout, stderr, exit_code = api.run(sys.argv[1:])
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
