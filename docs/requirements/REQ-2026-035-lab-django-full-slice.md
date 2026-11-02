# REQ-2026-035 lab-django 全量业务切片

| 项 | 值 |
|---|---|
| 提出人 | zcqiand |
| 提出日期 | 2026-11-02 |
| 优先级 | P1 |
| 状态 | 开发完成待验收（2026-11-03 AC-1..4 全过，验收签注+GA 翻转留人） |
| 关联 ADR | — |
| 先例 | REQ-2026-004（lab-go 全量切片，配方已验）/ REQ-2026-003（saas-go 同链）/ REQ-2026-030（本仓 contracts 首切片） |
| 关联 | tracker 5.127②/5.128（CT 注册三候选，人裁 2026-11-02 走 (a) 补全量面） |

## 1. 需求描述

> 人裁原话（AskUserQuestion 2026-11-02）：5.128 django CT 注册走「(a) django 补全量面」。

理解：lab-django 仓从 contracts 首切片态（5 op）推到全量业务面，与 rails/springboot/fastapi/go 同门对齐——shared 契约 120 op / 13 tag 全实现（本仓 `generated/api_manifest.json` 为路由 parity SSOT）、全量 route-parity、DB-First entity 链（24 表 pull-schema 收链）、lab CT 注册 django:5213、gate L0-L5 全绿。

### django 栈分叉面（相对 go 先例的差异，即本单核心风险面）

1. **工具链**：门全 python 家族工具链（ruff format/check / mypy strict 走 `scripts/mypy-django.py` 包装器 / pytest-django），依赖装全局 python（suite 钉版同源）；无 DB 注入面板差异——gate-inject 已表驱动（.env.test 通道）
2. **生成面**：DTO=datamodel-code-generator → `src/lab_management_system_django/contract/models/`；manifest=gen-manifest.py → `generated/api_manifest.json`（L4.codegen.idempotent strict 已接线，REQ-2026-030 批完成）；实现缝=手写 serializers/views/urls（serializer 从生成 DTO 变换）
3. **entity DB-First**：整库重建必带 pull-schema 收链（家族细则 §6.2）；列全 text（家族指纹：可空列必 `null=True`，Model `__init__` 缺省 `""` 撞 FK——REQ-2026-030 批在册）；`db_default` 走 PG 侧默认
4. **auth decode-only**（REQ-2026-030 已立语义）：bearer 只解 payload 不验签（nextjs oracle 同款）；401 信封 `{code:UNAUTHORIZED,...}`；登录代理 saas IdP 的 native-login 面随本批补齐（go REQ-2026-023 同款语义：saas 4xx→401 不透传、5xx→502 SAAS_UNAVAILABLE）
5. **测试基座**：pytest-django `django_db` 事务回滚不污染共库；conftest 覆写 `django_db_setup` 防 syncdb 污染家族库（X17 首航在册坑）；**token 租户 claim 真源=shared 种子行推导**（2026-11-02 三处修后纪律，禁 TENANT-001 字面量回潮）；lab_test 种子残留由 e2e purge HTTP 化（2026-11-02）与 CT cleanup-pg 双通道守护
6. **种子**：真源=shared `seeds/`（26 json，lab_test 24 表 4377 行快照）；测试库 `lab_test`（127.0.0.1:54321）

### 澄清记录

| 疑问 | 澄清结论 | 澄清人 | 日期 |
|---|---|---|---|
| 边界 | = rails 同门全量面（120 op parity）+ lab CT django:5213 注册；CT 无按域裁面机制（5.127② Recon 定谳），故「补全量」是注册的前提而非可选项 | zcqiand（AskUserQuestion 三候选裁定） | 2026-11-02 |

## 2. 验收标准

| 编号 | 场景（给定） | 操作（当） | 面预期（则） |
|---|---|---|---|
| AC-1 | shared openapi 120 op | 跑本仓 route-parity 契约门（`test_route_parity.py` 全量扩展） | ✅ 全部路由挂接、无契约外路由 |
| AC-2 | 本机 PG lab_dev | 跑 strict 幂等门 | ✅ gen-shared.sh 复放字节幂等（L4.codegen.idempotent strict exit 0） |
| AC-3 | lab_test 种子在位 | `python scripts/gate.py -p lab-management-system-django` | ✅ L0-L5 全绿；django_db 事务回滚不污染共库（rails gate L4 交叉仍绿） |
| AC-4 | 本机起 lab-django :5213 连 lab_dev + saas IdP :5101 | native-login→me→菜单冒烟 | ✅ live 探针全 200；lab CT live 新 member（django）收敛 |

## 3. 任务拆解

见 suite 仓 `docs/superpowers/plans/2026-11-02-django-lab-full-slice.md`（Task T1-T12）。

## 4. 功能影响

| 功能 ID | 功能名称 | 影响类型 | 说明 | 关联任务 |
|---|---|---|---|---|
| M00-M06 全部活跃 I 项（lab shared 树） | 租户/认证/资源/试验过程/基础数据/统计/检测能力 | 新增 | django 侧逐域交付，I 级随实现逐段 mirror 登记 | T2-T11 |

## 5. 人工验收记录

（待批交付后填写）
