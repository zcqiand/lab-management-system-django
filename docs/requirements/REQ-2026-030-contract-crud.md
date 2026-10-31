# REQ-2026-030 lab-django 合同管理首切片（M02.F01 全 CRUD 五 op）

| 项 | 值 |
|---|---|
| 提出人 | 用户 |
| 提出日期 | 2026-10-31 |
| 优先级 | P1 |
| 状态 | 已评审 |
| 关联 ADR | — |

## 1. 需求描述

> **用户原话**：「lab 首切片选 M04 合同 CRUD」（选项描述：harmonyos lab 先例——合同 CRUD 写片；读写面齐全，能一次验证 codegen 管线 + 写路径 + 路由 parity 全链）。

**我的理解**：lab-management-system-django 的第一个业务 REQ——合同 CRUD 全五 op（列表/创建/详情/更新/删除），消费 shared 契约 `contracts.tsp` 的 `/api/contracts` 面。功能树 SSOT 里合同管理在 **M02.F01**（模块总览：M02 资源管理—合同管理），用户选项文案的「M04」是本方选项标注笔误，树为准，见澄清记录。

### 澄清记录

| 疑问 | 澄清结论 | 澄清人 | 日期 |
|---|---|---|---|
| 选项写「M04 合同 CRUD」，合同在 M04 吗？ | 否——功能树 SSOT 合同管理=M02.F01（M04 是 F06-F09 码表）；按树实现 M02.F01，「M04」是选项标注笔误 | Claude 树核时确认，留人核 | 2026-10-31 |
| REQ 编号怎么取？ | 初取 029 **撞号**（saas-angular `REQ-2026-029-angular-full-feature-sync` 在先，suite commit 20e7eab 即其 T-3），2026-11-01 全家族扫证后改取 **030**（主系列 027=angular 首航、028=saas-django、029=saas-angular 全量同步，030 空） | Claude 取号修正，留人核 | 2026-11-01 |
| 分页语义按契约 @doc「不切片」还是 CT？ | 按 CT 仲裁：1-based（默认 page=1/pageSize=20，2026-09-16 T11 live 实证，nextjs oracle pageOf 切片）；契约 @doc「仅回显不切片」是陈旧描述（契约描述×生成器指纹在案），更新 shared 描述须人批，不在本 REQ | Claude 查 CT 与 oracle 时确认 | 2026-10-31 |
| 鉴权按什么形状？ | decode-only 不验签（nextjs bearer.ts 只解 payload；aspnetcore 才验签）+ tenant_id claim 必需，缺失/无效 401 信封 `{code:"UNAUTHORIZED",message:"tenant_id claim is required (ADR-0019)"}`（ADR-0019，禁 demo 字面量兜底） | Claude 查 require-tenant/bearer.ts 时确认 | 2026-10-31 |

## 2. 验收标准

| 编号 | 场景（给定） | 操作（当） | 预期（则） |
|---|---|---|---|
| AC-1 | 已认证（token 含 tenant_id），本租户有 seed 合同 | `GET /api/contracts` | 200 + Page 信封（page=1/pageSize=20 默认，1-based 切片）；只含本租户行 |
| AC-2 | 已认证，keyword/status 查询参数 | `GET /api/contracts?keyword=&status=` | keyword ilike 匹配 contractCode/projectName；status 精确匹配 |
| AC-3 | 已认证，body 含必填 6 项 | `POST /api/contracts` | 201 + 全字段行；id 服务端生成；tenant_id 取 token claim（body.tenantId 忽略，ADR-0019）；status 缺省 active |
| AC-4 | 已认证，body 缺任一必填 | `POST /api/contracts` | 400 信封 `{code:"BAD_REQUEST",message:6 必填项提示}`（与 nextjs oracle 逐字一致） |
| AC-5 | 已认证，ID 存在 / 不存在 | `GET /api/contracts/{id}` | 200 全字段 / 404 `{code:"NOT_FOUND",message:"Contract not found"}` |
| AC-6 | 已认证，ID 存在，body 局部字段 | `PUT /api/contracts/{id}` | 200 + 局部合并更新（Object.assign 语义），404 if 不存在 |
| AC-7 | 已认证，ID 存在 | `DELETE /api/contracts/{id}` | 204 空体；重复删 404（幂等） |
| AC-8 | 未认证 / token 无 tenant_id claim | 任一端点 | 401 信封 `UNAUTHORIZED`（固定形状，§3 禁兜底） |
| AC-9 | 五 op 全落地 | — | lab contract-test TARGETS 具备注册条件（全 CRUD 覆盖测试面；注册动作随 live 里程碑批） |

## 3. 任务拆解

| 任务 ID | 任务描述 | 类型 | 负责人 | 预估 | 状态 |
|---|---|---|---|---|---|
| T-1 | codegen 管线复刻（saas-django 先例移植 + lab 适配：gen-shared.sh（`=` 键 sanitize 落 _work/ + datamodel-codegen modular 目录输出）+ gen-manifest.py（BaseLoader）） | 开发 | 待定 | 0.5d | 已完成（2026-10-31，生成区+manifest 落盘，管线全步绿） |
| T-2 | models（contracts 全 text 列 managed=False，DB-First） | 开发 | 待定 | 0.5d | 已完成（2026-10-31；可空列 null=True——Model.__init__ 非 null 文本缺省 "" 会撞 contracts_specialty_fk，nextjs oracle 缺键落 NULL 同款） |
| T-3 | serializers + views + urls（五 op，decode-only 鉴权 + 租户收口 + 1-based 分页切片 + 过滤） | 开发 | 待定 | 1d | 已完成（2026-10-31，auth.py/errors.py 挂仓身份包 `lab_management_system_django/`） |
| T-4 | 测试挂 `@pytest.mark.fn`（I01-I05，覆盖 AC-1..8）+ 路由 parity | 开发 | 待定 | 0.5d | 已完成（2026-10-31；红灯证据在案：首跑 20 failed / 4 passed，绿灯 24 passed，全门 L0-L5 绿） |
| T-5 | lab contract-test TARGETS 注册（django=5213）——本切片全 CRUD 已覆盖测试面，注册随 live 里程碑批执行 | 开发 | 待定 | 0.25d | 缓期（人裁：随 live 里程碑批，CT 治理「声明即必须可达」，注册后 django 后端须 live 可达） |

## 4. 功能影响（需求与功能对齐的唯一位置）

> ID 均已在 `docs/functions/function-tree.md` 镜像登记（shared BASE 已有 I01-I05）；令牌已焚。

| 功能 ID | 功能名称 | 影响类型 | 说明 | 关联任务 |
|---|---|---|---|---|
| M02.F01 | 合同管理 | 变更 | 首切片实现 5/5 子项 | T-1..T-5 |
| M02.F01.I01 | 合同列表 | 新增（登记） | 镜像登记，状态=规划 | T-1..T-5 |
| M02.F01.I02 | 合同详情 | 新增（登记） | 镜像登记，状态=规划 | T-1..T-5 |
| M02.F01.I03 | 创建合同 | 新增（登记） | 镜像登记，状态=规划 | T-1..T-5 |
| M02.F01.I04 | 更新合同 | 新增（登记） | 镜像登记，状态=规划 | T-1..T-5 |
| M02.F01.I05 | 删除合同 | 新增（登记） | 镜像登记，状态=规划 | T-1..T-5 |

## 5. 流程影响

无——本仓尚无 flow-function-map（首个流程随首切片建立）。

## 6. 风险与回滚

| 风险 | 影响面 | 缓解 | 回滚方式 |
|---|---|---|---|
| 契约 @doc「不切片」与 CT 仲裁「1-based 切片」分叉 | T-3 | 按 CT 仲裁实现；shared 描述更新另行走人批 | — |
| lab 全 text 列（时间戳/主键无 DB 默认） | T-2 | id/时间戳应用侧生成（uuid4 + ISO），与 nextjs oracle 一致 | — |
| contract-test 注册后写比对撞 UNIQUE(tenant_id,contract_code) | T-5 | CT 已有 uniqueName + cleanup 机制 | — |

---

I 级登记已在功能树镜像完成（mirror 免批，令牌已焚；sync_files 见提案）。
