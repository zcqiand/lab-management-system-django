"""pytest 早期插件——比 conftest 更早，抢在 pytest-django 初始化前。

pytest-django 是入口点插件，在 pytest_load_initial_conftests 期（早于任何
conftest 导入）就真实 import DJANGO_SETTINGS_MODULE；本项目 settings fail-fast
（suite-hard-rules §1）无兜底，所以必须把 `.env.test`（已入库测试夹具，
fastapi 仓先例）在它之前灌进 os.environ。pytest 的 `-p` 插件在预解析期加载，
先于入口点插件——L4 与 trace_cmd 都经 `-p env_bootstrap` 挂本模块。

只影响测试/静态检查进程，不改变运行时语义。
"""

from __future__ import annotations

import os
from pathlib import Path

for line in (Path(__file__).resolve().parent / ".env.test").read_text(
    encoding="utf-8"
).splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip())
