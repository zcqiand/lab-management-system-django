# CLAUDE.md — 实验室管理 Django 版

> 书稿配套仓 + harness 门禁仓双身份。入口，不是手册。L0 门强制上限 60 行。
> 本仓为《（书稿信息待补）》案例（待补）（实验室管理 Django 版）的可运行配套工程，是书稿代码块的 **source of truth**。

## 1. 项目定位

实验室管理 Django 版（`lab-management-system-django`，技术栈 `django`）。一句话定位见 README.md。

## 2. 铁律

- **TDD**：每个模块先写失败测试 → 跑确认失败 → 实现 → 跑确认绿 → commit
- **版本钉死**：依赖与 `version-lock.json` 的 `version_lock` 一致；不引入 lock 外的库
- **tag 即放行**：全量回归绿后打 `v<MAJOR>.<MINOR>.<PATCH>-<YYYYMMDD>`（如 `v0.3.54-20260826`）
- **mock-friendly**：安装 + 测试必须在无 Key、无 Docker、无网下全绿
- **功能清单是锚点**：改 `docs/functions/function-tree.md` 走 `/tree-change` 提案，由人批准；
  改功能与改功能清单必须同一个 commit；废弃只改状态，编号永不复用；禁止给 skip 的测试挂功能 ID

- 禁止 Any 与 type: ignore（除非附 ADR 说明）
- 禁止在未写测试的情况下提交实现代码
- 禁止使用可变默认参数
- 路由/视图必须显式声明 serializer_class 与 queryset（或 get_queryset），禁止裸 dict / 裸 ORM 对象直出响应
- 业务身份字段缺失必须 401/403，禁止兜底到 demo 字面量（suite 硬规则 §3）
- 禁止 env 默认值兜底（suite-hard-rules §1）：settings 一律 fail-fast
- API 面只认 shared 契约生成物（suite-hard-rules §4），禁止手写与契约漂移的端点

## 3. 技术栈与版本（钉死于 version-lock.json）

Django 5 + Django REST Framework —— ruff / mypy(strict, django-stubs) / pytest(-django)。X17 扩展槽 saas=5113 / lab=5213（SERVER_PORT 家族统一 key，进 deploy 链时启用）。明细见 `version-lock.json` 与 README.md 技术栈表。

门禁命令见 `.harness/stack.json`。**不要改它来让门变松。**

## 4. 验收

- 在 **suite 根目录** 跑 `python scripts/gate.py -p lab-management-system-django`；exit 0 才算完成
- 本地命令见 README.md「快速开始」

## 5. 指向别处

- 功能清单（唯一锚点） → `docs/functions/function-tree.md`
- 需求 → 任务 → 功能影响 → `docs/requirements/`
- 流程/设计 与功能对齐 → `docs/design/`（人评审，机器只查引用）
- 决策背景 → `docs/adr/`；编码细则 → `docs/conventions/`（不进主上下文）
- 待办与迭代方向 → `PLAN.md`；版本变更 → `CHANGELOG.md`

## 6. 工作循环

0. **开工前分诊**：先过 `using-skills`，把激活 skill 的清单落成 todo。
   顺序：规格(brainstorming)→计划(writing-plans)→测试先红(red-first)→实现(executing-plans)
1. 读 `.state/session.json` 恢复上下文
2. 最小改动
3. 跑 `python scripts/gate.py -p lab-management-system-django`；exit 1 回到第 2 步；exit 2 停下问人
4. `/handoff` 更新 `.state/session.json`
