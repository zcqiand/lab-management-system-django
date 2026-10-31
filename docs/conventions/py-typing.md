# Python 类型细则

> 什么时候读我：由 `.claude/skills/py-typing/SKILL.md` 引用。不要预加载。

## mypy --strict 已强制的不写在这里

## 已拍板的取舍

| 场景 | 本项目怎么做 |
|---|---|
| 函数参数是容器 | 用 `Sequence` / `Mapping`，不用 `list` / `dict` |
| 返回值是容器 | 用具体类型 `list` / `dict` |
| 结构化子类型 | `Protocol`，不为类型而继承 ABC |
| 固定形状的字典 | `TypedDict` |
| 类型收窄 | `TypeGuard`，不撒 `assert isinstance` |

## `Any` 与 `type: ignore`

mypy 认这两个，**门禁不会拦**。所以它们只能靠纪律。
用它们必须：同行注释给出理由 + 写一条 ADR。

没有 ADR 的 `type: ignore`，code-reviewer 应当列为阻断项。
