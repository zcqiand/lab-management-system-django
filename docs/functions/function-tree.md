# 功能清单（Function Tree）— 实验室管理 Django 版

> **全体系唯一锚点。** 需求、流程、设计、测试都引用这里的 ID。
> 不在这里的 ID 是悬空引用，L5 门会拦。**改功能，先改这份表。**

## 编号规则

| 层级 | 名称 | 格式 | 含义 |
|---|---|---|---|
| 一级 | 功能模块 | `M0x` | 业务域边界，通常对应一级菜单 |
| 二级 | 功能 | `M0x.F0y` | 一个完整业务步骤 / 独立闭环流程 / 数据管理页面 |
| 三级 | 功能子项 | `M0x.F0y.I0z` | 技术交付单元 / 权限挂载点。对应一个 API 接口、页面组件、图表区块或权限控制点 |

**硬规则**

1. 编号单调递增，永不复用。废弃改状态，不删行。
2. 子项编号必须以父级为前缀。
3. 一个子项 = 一个权限点。权限码即 ID，不另套一套编码。
4. 拆不出子项的功能 → 它其实是子项，往上并。子项超 20 个 → 它其实是模块，往下拆。

**状态**：`规划` | `开发中` | `已上线` | `已废弃`
**子项类型**：`页面` | `标签页` | `查询` | `按钮` | `报表` | `接口`
**交付**：`前端+后端` | `仅前端` | `仅后端`

---

## 本仓角色

**消费仓（瘦镜像）**。ID 真源 = `lab-management-system-shared` BASE 树。
本仓树先行镜像到**模块 + 功能级**；I 级子项**不预先铺满**——首个 REQ 进来时，
仅把该 REQ 涉及的 I 级经 `tree_change.py --apply`（mirror 免批，reason 引 REQ 编号）登记进来，随切片生长（ktor/go 先例）。

---

## 模块总览

| 模块 ID | 模块名称 | 说明 | 状态 |
|---|---|---|---|
| M00 | 租户管理 | 当前用户关联租户列表、登录选租户、切换租户 | 规划 |
| M01 | 认证管理 | 权限管理（RBAC/路由守卫/动态菜单）、认证（登录/SSO/JWT） | 规划 |
| M02 | 资源管理 | 合同管理 | 规划 |
| M03 | 试验过程管理 | 接样 → 任务分配 → 数据录入 → 报告审核 → 批准 → 发放 → 归档 | 规划 |
| M04 | 基础数据 | 型号/规格/等级/牌号维护 | 规划 |
| M05 | 数据统计 | 报告汇总表（按报告名称） | 开发中 |
| M06 | 检测能力 | 检测专项/项目/参数/标准/计算方法/技术要求/报告名称/参数界面 | 规划 |

---


## M00 租户管理

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M00.F01 | 当前用户会话 | 当前用户信息 + 关联租户列表 + 当前选中租户（GET /auth/me） | 开发中 |
| M00.F02 | 登录选租户 | 登录后选择租户，换发携带 tenant_id claim 的 token（POST /auth/switch-tenant） | 开发中 |

### M00.F01 当前用户会话

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M00.F01.I01 | 当前会话 | 接口 | 前端+后端 | GET /api/auth/me：user + 关联租户列表 + currentTenantId（token tenant_id claim，缺省 TENANT-001） | 开发中 |

### M00.F02 登录选租户

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M00.F02.I01 | 选租户换发 | 接口 | 前端+后端 | POST /api/auth/switch-tenant：校验租户归属后换发携带 tenant_id claim 的 token | 开发中 |


## M01 认证管理

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M01.F04 | 权限管理 | RBAC 角色权限、路由守卫、权限指令、动态菜单（身份平台下发） | 开发中 |
| M01.F05 | 认证管理 | OAuth 2.0 授权码 SSO（client_secret 后端持）+ lab 自家 JWT 签发，saas token 不出 lab 后端 | 开发中 |

### M01.F04 权限管理

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M01.F04.I01 | 动态菜单 | 接口 | 前端+后端 | GET /api/auth/menus：按角色下发导航树（5 根节点，镜像 lab-msw） | 开发中 |
| M01.F04.I02 | 权限集 | 接口 | 前端+后端 | GET /api/auth/permissions：RBAC 权限串列表（admin 全量 11 项） | 开发中 |

### M01.F05 认证管理

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M01.F05.I02 | SSO 跳转 | 接口 | 前端+后端 | GET /api/auth/sso/authorize：RFC 6749 §10.12 标准 state（前端生成、原样透传 saas 回显、前端比对），forward saas POST /api/v1/oauth/authorize 拿 code | 开发中 |
| M01.F05.I03 | SSO 回调 | 接口 | 前端+后端 | POST /api/auth/sso/callback:saas POST /api/v1/oauth/token 用一次性 code 换 token,再 /me/whoami + /me/tenants 拿 user,membership 信 saas;首次 SSO 按 email upsert 到 lab directory;state 校验在前端回跳比对 | 开发中 |
| M01.F05.I04 | 刷新 token | 接口 | 前端+后端 | POST /api/auth/refresh:lab refresh token 是 HS256 JWT(typ=refresh),内嵌 saas refresh token;调 saas POST /api/v1/oauth/token grantType=refresh_token 续,再签新 lab JWT | 开发中 |
| M01.F05.I05 | 登出 | 接口 | 前端+后端 | POST /api/auth/logout：无状态 JWT 服务端无 session，前端清存储 | 开发中 |
| M01.F05.I06 | 原生登录 | 接口 | 前端+后端 | POST /api/auth/native-login：非浏览器客户端（iOS/Android 原生表单）密码通道，REQ-2026-003 Q4-C 人裁（2026-09-28，非恢复已废弃 I01 web 密码端点）；REQ-2026-023 变更（2026-10-11 人裁方案 A）：校验委托 saas IdP 代理——请求体账密调 saas /api/v1/auth/login（clientId=lab-management），lab 自家 JWT 重签与 LoginResponse 契约形状不变，LAB_AUTH_DEV_PASSWORD 全家族退役 | 开发中 |


## M02 资源管理

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M02.F01 | 合同管理 | 合同 CRUD、工程信息维护 | 开发中 |

### M02.F01 合同管理

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M02.F01.I01 | 合同列表 | 接口 | 前端+后端 | GET /api/contracts?keyword=&status=：按 tenant 收口 + 2 过滤 + 1-based 分页切片（CT T11 仲裁） | 开发中 |
| M02.F01.I02 | 合同详情 | 接口 | 前端+后端 | GET /api/contracts/{id}：404 if 不存在 | 开发中 |
| M02.F01.I03 | 创建合同 | 接口 | 前端+后端 | POST /api/contracts：必填 6 项 400，status 默认 ACTIVE，tenant_id 取 token claim | 开发中 |
| M02.F01.I04 | 更新合同 | 接口 | 前端+后端 | PUT /api/contracts/{id}：局部合并 | 开发中 |
| M02.F01.I05 | 删除合同 | 接口 | 前端+后端 | DELETE /api/contracts/{id}：204；重复删 404 | 开发中 |


## M03 试验过程管理

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M03.F01 | 接样管理 | 接样单 CRUD、报告类别关联、流程状态 | 开发中 |
| M03.F02 | 任务分配 | 接样提交后安排检测人员/计划日期，提交进入数据录入；任务字段挂 SampleReceipt | 开发中 |
| M03.F03 | 数据录入 | 样品检测数据录入 | 开发中 |
| M03.F05 | 报告审核 | 报告审核流程 | 开发中 |
| M03.F06 | 报告批准 | 报告批准流程 | 开发中 |
| M03.F07 | 报告发放 | 报告发放流程 | 开发中 |
| M03.F08 | 报告归档 | 报告归档流程 | 开发中 |
| M03.F09 | 接样单详情 | 接样单查看（接样信息+样品信息+检测数据） | 规划 |

### M03.F01 接样管理

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F01.I01 | 接样单列表 | 接口 | 前端+后端 | GET /api/receipts?contractId=&flowStatus=&keyword=：按 tenant 收口 + 3 过滤 | 开发中 |
| M03.F01.I02 | 接样单详情 | 接口 | 前端+后端 | GET /api/receipts/{id}：返回 SampleReceipt（含 flow_history）；**shared-with: M03.F05.I02 / M03.F06.I02 / M03.F07.I02 / M03.F08.I02 / M03.F09.I01** | 开发中 |
| M03.F01.I03 | 创建接样单 | 接口 | 前端+后端 | POST /api/receipts：contract_id FK 必存在；flow_status=receiving 起步；flow_history=[] | 开发中 |
| M03.F01.I04 | 更新接样单 | 接口 | 前端+后端 | PUT /api/receipts/{id}：PATCH 语义 | 开发中 |
| M03.F01.I05 | 删除接样单 | 接口 | 前端+后端 | DELETE /api/receipts/{id}：CASCADE 删除下属 samples | 开发中 |
| M03.F01.I06 | 接样单流程历史 | 接口 | 前端+后端 | GET /api/receipts/{id}/history：返回 FlowHistoryEntry[]（jsonb 展开为 List） | 开发中 |
| M03.F01.I07 | 接样单 ext 字段补录 | 接口 | 前端+后端 | PUT /api/samples/{id}/ext：UpdateSampleExtRequest{ext} 按当前类别 extFields 补录持久化到 Sample.ext | 开发中 |
| M03.F01.I08 | 接样-提交 | 接口 | 前端+后端 | POST /api/receipts/receiving/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I09 退回/I10 撤回语义并入本行；RETURN 前置阶段退回无前置则 422、WITHDRAW 提交人撤回回到原阶段；7 阶段全 act 模式） | 开发中 |

### M03.F02 任务分配

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F02.I01 | 任务分配 | 接口 | 前端+后端 | PUT /api/receipts/{id}/task：AssignTaskRequest 设 assigneeId/Name/plannedTestDate；非 receiving 阶段不自动 advance | 开发中 |
| M03.F02.I05 | 任务分配-提交 | 接口 | 前端+后端 | POST /api/receipts/assigning/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I06 退回/I07 撤回语义并入本行；RETURN 退回到 receiving；7 阶段全 act 模式） | 开发中 |

### M03.F03 数据录入

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F03.I01 | 样品列表 | 接口 | 前端+后端 | GET /api/samples?receiptId=&keyword=：tenant + 2 过滤 | 开发中 |
| M03.F03.I02 | 样品详情 | 接口 | 前端+后端 | GET /api/samples/{id} | 开发中 |
| M03.F03.I03 | 创建样品 | 接口 | 前端+后端 | POST /api/samples：receipt_id FK 必存在；ext 默认 {} | 开发中 |
| M03.F03.I04 | 更新样品 | 接口 | 前端+后端 | PUT /api/samples/{id}：PATCH 语义 | 开发中 |
| M03.F03.I05 | 删除样品 | 接口 | 前端+后端 | DELETE /api/samples/{id}：204 | 开发中 |
| M03.F03.I06 | 检测记录列表 | 接口 | 前端+后端 | GET /api/test-records?sampleId=&page=&pageSize=：tenant 收口 + sampleId 过滤 + 分页；data-fn=nextjs/react/vue 仓 test-records 页面 | 开发中 |
| M03.F03.I07 | 检测记录详情 | 接口 | 前端+后端 | GET /api/test-records/{id}：返回 TestRecord | 开发中 |
| M03.F03.I08 | 创建检测记录 | 接口 | 前端+后端 | POST /api/test-records：sampleId/parameterCode/requirement/result 必填；tenant 从 token claim 注入 | 开发中 |
| M03.F03.I09 | 更新检测记录 | 接口 | 前端+后端 | PUT /api/test-records/{id}：PATCH 语义，未传字段保留 | 开发中 |
| M03.F03.I10 | 删除检测记录 | 接口 | 前端+后端 | DELETE /api/test-records/{id}：204 if exists | 开发中 |
| M03.F03.I11 | 检测记录改判 | 接口 | 前端+后端 | PATCH /api/test-records/{id}/verdict：人工改判（2026-09-18 以 .tsp 为准修正动词，原误写 PUT；M03.F05/F06 报告流程可触发） | 开发中 |
| M03.F03.I12 | 数据录入-提交 | 接口 | 前端+后端 | POST /api/receipts/data-entry/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I13 退回/I14 撤回语义并入本行；RETURN 退回到 assigning；7 阶段全 act 模式） | 开发中 |

### M03.F05 报告审核

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F05.I07 | 报告审核-提交 | 接口 | 前端+后端 | POST /api/receipts/review/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I08 退回/I09 撤回语义并入本行；4 阶段全 act 合并方案 B） | 开发中 |

### M03.F06 报告批准

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F06.I05 | 报告批准-提交 | 接口 | 前端+后端 | POST /api/receipts/approve/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I06 退回/I07 撤回语义并入本行；4 阶段全 act 合并方案 B） | 开发中 |

### M03.F07 报告发放

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F07.I05 | 报告发放-提交 | 接口 | 前端+后端 | POST /api/receipts/issuance/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I06 退回/I07 撤回语义并入本行；4 阶段全 act 合并方案 B） | 开发中 |

### M03.F08 报告归档

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M03.F08.I05 | 报告归档-提交 | 接口 | 前端+后端 | POST /api/receipts/archived/act，body.action={SUBMIT、RETURN、WITHDRAW} 三动作统一（2026-09-18：I06 退回/I07 撤回语义并入本行；4 阶段全 act 合并方案 B） | 开发中 |


## M04 基础数据

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M04.F06 | 型号维护 | InspectionModel 实体码表维护，列表按检测专项过滤 | 开发中 |
| M04.F07 | 规格维护 | InspectionSpec 实体码表维护，列表按检测专项过滤 | 开发中 |
| M04.F08 | 等级维护 | InspectionGrade 实体码表维护，列表按检测专项过滤 | 开发中 |
| M04.F09 | 牌号维护 | InspectionBrand 实体码表维护，列表按检测专项过滤 | 开发中 |

### M04.F06 型号维护

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M04.F06.I01 | 型号列表 | 接口 | 前端+后端 | GET /api/catalog/models?page=&pageSize=&inspectionObjectCode=&keyword=：`Page<InspectionModel>`，按 tenant 收口 + 2 过滤 | 开发中 |
| M04.F06.I02 | 创建型号 | 接口 | 前端+后端 | POST /api/catalog/models：body CreateCatalogEntryRequest（code/name 必填 + 可选 inspectionObjectCode/remark/sortOrder），返回 InspectionModel | 开发中 |
| M04.F06.I03 | 更新型号 | 接口 | 前端+后端 | PUT /api/catalog/models/{code}：body UpdateCatalogEntryRequest（PATCH 语义，未传字段保留），404 if 不存在 | 开发中 |
| M04.F06.I04 | 删除型号 | 接口 | 前端+后端 | DELETE /api/catalog/models/{code}：204；FK 被 technical_requirements.model 引用时 DB SET NULL | 开发中 |

### M04.F07 规格维护

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M04.F07.I01 | 规格列表 | 接口 | 前端+后端 | GET /api/catalog/specs?page=&pageSize=&inspectionObjectCode=&keyword=：`Page<InspectionSpec>` | 开发中 |
| M04.F07.I02 | 创建规格 | 接口 | 前端+后端 | POST /api/catalog/specs | 开发中 |
| M04.F07.I03 | 更新规格 | 接口 | 前端+后端 | PUT /api/catalog/specs/{code} | 开发中 |
| M04.F07.I04 | 删除规格 | 接口 | 前端+后端 | DELETE /api/catalog/specs/{code} | 开发中 |

### M04.F08 等级维护

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M04.F08.I01 | 等级列表 | 接口 | 前端+后端 | GET /api/catalog/grades?page=&pageSize=&inspectionObjectCode=&keyword=：`Page<InspectionGrade>` | 开发中 |
| M04.F08.I02 | 创建等级 | 接口 | 前端+后端 | POST /api/catalog/grades | 开发中 |
| M04.F08.I03 | 更新等级 | 接口 | 前端+后端 | PUT /api/catalog/grades/{code} | 开发中 |
| M04.F08.I04 | 删除等级 | 接口 | 前端+后端 | DELETE /api/catalog/grades/{code} | 开发中 |

### M04.F09 牌号维护

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M04.F09.I01 | 牌号列表 | 接口 | 前端+后端 | GET /api/catalog/brands?page=&pageSize=&inspectionObjectCode=&keyword=：`Page<InspectionBrand>` | 开发中 |
| M04.F09.I02 | 创建牌号 | 接口 | 前端+后端 | POST /api/catalog/brands | 开发中 |
| M04.F09.I03 | 更新牌号 | 接口 | 前端+后端 | PUT /api/catalog/brands/{code} | 开发中 |
| M04.F09.I04 | 删除牌号 | 接口 | 前端+后端 | DELETE /api/catalog/brands/{code} | 开发中 |


## M05 数据统计

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M05.F01 | 报告汇总 | 按报告类别输出试验报告汇总表 | 开发中 |

### M05.F01 报告汇总

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M05.F01.I01 | 报告汇总 | 查询 | 前端+后端 | GET /api/summary?categoryCode=&dateFrom=&dateTo=：categoryCode=ALL 不过滤，否则按报告类别过滤当前租户接样单；输出 SummaryData{summaryName, columns(6), rows} | 开发中 |
| M05.F01.I06 | 仪表盘统计基础端点 | 查询 | 前端+后端 | GET /api/summary/stats 基础字段：contractCount/receiptCount/sampleCount + 报告状态 3 桶（draft=receiving+task+data_entry；reviewing=review+approval；issued=issuance+archived）+ pendingTaskCount。ADR-0033 阶段二从后端仓 M05.F02.I01 下沉 BASE（四方已上线的事实先行入树，I03/I04 是本端点的扩展字段） | 开发中 |


## M06 检测能力

| 功能 ID | 功能名称 | 说明 | 状态 |
|---|---|---|---|
| M06.F01 | 检测专项 | InspectionSpecialty CRUD（检测能力字典根） | 开发中 |
| M06.F02 | 检测项目 | InspectionObject CRUD + 专项/参数关联 | 开发中 |
| M06.F03 | 检测参数 | InspectionParameter CRUD + 标准/参数关联 | 开发中 |
| M06.F04 | 检测标准 | InspectionStandard CRUD（含状态：active/superseded/draft） | 开发中 |
| M06.F05 | 计算方法 | CalculationMethod 维护（复合主键，算法类型 + 公式） | 开发中 |
| M06.F06 | 技术要求 | TechnicalRequirement 维护，按四维度匹配；brand/model/grade/spec 改为 FK 引用实体 | 开发中 |
| M06.F07 | 报告名称 | InspectionReportName CRUD + extFields 模板 + 关联标准/参数 | 开发中 |

### M06.F05 计算方法

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F05.I01 | 计算方法列表 | 接口 | 前端+后端 | GET /api/calculation-methods?inspectionObjectCode=&inspectionParameterCode=：平台级（无 tenant 过滤），裸数组 | 开发中 |
| M06.F05.I02 | 计算方法详情 | 接口 | 前端+后端 | GET /api/calculation-methods/{inspectionObjectCode}/{inspectionParameterCode}：复合主键 | 开发中 |
| M06.F05.I03 | 创建计算方法 | 接口 | 前端+后端 | POST /api/calculation-methods：body CreateCalculationMethodRequest，algorithmType 默认 MANUAL、specimenCount 默认 1 | 开发中 |
| M06.F05.I04 | 更新计算方法 | 接口 | 前端+后端 | PUT /api/calculation-methods/{...}：PATCH 语义（truthy/strict 双判定） | 开发中 |
| M06.F05.I05 | 删除计算方法 | 接口 | 前端+后端 | DELETE /api/calculation-methods/{...}：204 | 开发中 |

### M06.F06 技术要求

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F06.I01 | 技术要求列表 | 接口 | 前端+后端 | GET /api/technical-requirements?inspectionObjectCode=&inspectionParameterCode=&judgmentStandardCode=&verificationStatus=：tenant 收口 + 4 过滤，裸数组 | 开发中 |
| M06.F06.I02 | 技术要求详情 | 接口 | 前端+后端 | GET /api/technical-requirements/{object}/{param}/{standard}：复合三键 | 开发中 |
| M06.F06.I03 | 创建技术要求 | 接口 | 前端+后端 | POST /api/technical-requirements：tenant 从 token claim 注入；默认值 numeric/≥/manual/draft | 开发中 |
| M06.F06.I04 | 更新技术要求 | 接口 | 前端+后端 | PUT /api/technical-requirements/{...}：PATCH 语义 | 开发中 |
| M06.F06.I05 | 删除技术要求 | 接口 | 前端+后端 | DELETE /api/technical-requirements/{...}：204 | 开发中 |

### M06.F07 报告名称

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F07.I01 | 报告名称列表 | 接口 | 前端+后端 | GET /api/report-names?page=&pageSize=&keyword=：`Page<InspectionReportName>`，按 code/name 模糊 | 开发中 |
| M06.F07.I02 | 报告名称详情 | 接口 | 前端+后端 | GET /api/report-names/{code}：返回 InspectionReportName（含 extFields 反序列化的 `List<ExtFieldDef>`） | 开发中 |
| M06.F07.I03 | 创建报告名称 | 接口 | 前端+后端 | POST /api/report-names：code/name 必填；extFields 默认 [] | 开发中 |
| M06.F07.I04 | 更新报告名称 | 接口 | 前端+后端 | PUT /api/report-names/{code}：PATCH 语义 | 开发中 |
| M06.F07.I05 | 删除报告名称 | 接口 | 前端+后端 | DELETE /api/report-names/{code}：204 if exists | 开发中 |
| M06.F07.I06 | 项目↔报告名称 link | 接口 | 前端+后端 | POST /api/report-names/links/object：建立 object→report-name 关联，remark 可选 | 开发中 |
| M06.F07.I07 | 报告名称↔标准 link | 接口 | 前端+后端 | POST /api/report-names/links/standard：建立 report-name→standard(role) 关联，role 必填 | 开发中 |
| M06.F07.I08 | 报告名称↔参数 link | 接口 | 前端+后端 | POST /api/report-names/links/parameter：建立 report-name→parameter 关联 | 开发中 |
| M06.F08 | 参数界面 | ParamInterface 维护 + 参数↔界面 link | 开发中 |

### M06.F08 参数界面

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F08.I01 | 参数界面列表 | 接口 | 前端+后端 | GET /api/param-interfaces?page=&pageSize=&keyword=：`Page<ParamInterface>`，按 code/name 模糊 | 开发中 |
| M06.F08.I02 | 参数界面详情 | 接口 | 前端+后端 | GET /api/param-interfaces/{code}：返回 ParamInterface（含 config 反序列化的 Map<String,Object>） | 开发中 |
| M06.F08.I03 | 创建参数界面 | 接口 | 前端+后端 | POST /api/param-interfaces：code/componentPath 必填；config 默认 {} | 开发中 |
| M06.F08.I04 | 更新参数界面 | 接口 | 前端+后端 | PUT /api/param-interfaces/{code}：PATCH 语义 | 开发中 |
| M06.F08.I05 | 删除参数界面 | 接口 | 前端+后端 | DELETE /api/param-interfaces/{code}：204 if exists | 开发中 |
| M06.F08.I06 | 参数↔界面 link | 接口 | 前端+后端 | POST /api/param-interfaces/links：建立 parameter→interface 关联，reportNameCode/config 可选（config 走 jsonb） | 开发中 |

### M06.F01 检测专项

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F01.I01 | 专项列表 | 接口 | 前端+后端 | GET /api/inspection/specialties?page=&pageSize=&keyword=：`Page<InspectionSpecialty>`，按 code/name 模糊匹配，平台级 | 开发中 |
| M06.F01.I02 | 创建专项 | 接口 | 前端+后端 | POST /api/inspection/specialties：code/officialNo/name 必填；isOfficial/enabled 默认 true；sortOrder 默认 0 | 开发中 |
| M06.F01.I03 | 更新专项 | 接口 | 前端+后端 | PUT /api/inspection/specialties/{code}：PATCH 语义，未传字段保留 | 开发中 |
| M06.F01.I04 | 删除专项 | 接口 | 前端+后端 | DELETE /api/inspection/specialties/{code}：204 if exists，否则 404 | 开发中 |
| M06.F01.I05 | 项目↔标准 link | 接口 | 前端+后端 | POST /api/inspection/links/object-standard：建立 object→standard(role) 关联，role 必填（TESTING/JUDGMENT） | 开发中 |
| M06.F01.I06 | 项目↔标准 unlink | 接口 | 前端+后端 | DELETE /api/inspection/links/object-standard：404 if 不存在 | 开发中 |
| M06.F01.I07 | 项目↔标准 列表 | 接口 | 前端+后端 | GET /api/inspection/links/object-standard?inspectionObjectCode=&role=：`Page<ObjectStandardLink>`，按 objectCode/role 过滤 | 开发中 |

### M06.F02 检测项目

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F02.I01 | 项目列表 | 接口 | 前端+后端 | GET /api/inspection/objects?page=&pageSize=&inspectionSpecialtyCode=&keyword=：`Page<InspectionObject>`，按 code/name 模糊 + 专项过滤 | 开发中 |
| M06.F02.I02 | 创建项目 | 接口 | 前端+后端 | POST /api/inspection/objects：code/inspectionSpecialtyCode/sourceProjectNo/sourceProjectName/name 必填；isOptionalForQualification 默认 false；isOfficial/enabled 默认 true | 开发中 |
| M06.F02.I03 | 更新项目 | 接口 | 前端+后端 | PUT /api/inspection/objects/{code}：PATCH 语义 | 开发中 |
| M06.F02.I04 | 删除项目 | 接口 | 前端+后端 | DELETE /api/inspection/objects/{code}：204 if exists | 开发中 |
| M06.F02.I05 | 专项↔项目 link | 接口 | 前端+后端 | POST /api/inspection/links/specialty-object：建立 specialty→object 关联，remark 可选 | 开发中 |
| M06.F02.I06 | 专项↔项目 unlink | 接口 | 前端+后端 | DELETE /api/inspection/links/specialty-object：404 if 不存在 | 开发中 |
| M06.F02.I07 | 项目↔参数 link | 接口 | 前端+后端 | POST /api/inspection/links/object-parameter：建立 object→parameter 关联，qualificationLevel 默认 QUALIFIED，sourcePage/remark 可选 | 开发中 |
| M06.F02.I08 | 项目↔参数 unlink | 接口 | 前端+后端 | DELETE /api/inspection/links/object-parameter：404 if 不存在 | 开发中 |
| M06.F02.I09 | 专项↔项目 列表 | 接口 | 前端+后端 | GET /api/inspection/links/specialty-object?inspectionSpecialtyCode=：`Page<SpecialtyObjectLink>`，按专项 code 过滤 | 开发中 |
| M06.F02.I10 | 项目↔参数 列表 | 接口 | 前端+后端 | GET /api/inspection/links/object-parameter?inspectionObjectCode=&inspectionParameterCode=：`Page<ObjectParameterLink>`，按 objectCode/parameterCode 过滤 | 开发中 |

### M06.F03 检测参数

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F03.I01 | 参数列表 | 接口 | 前端+后端 | GET /api/inspection/parameters?page=&pageSize=&keyword=&sourceType=：`Page<InspectionParameter>`，按 code/name 模糊 + sourceType 过滤（official/custom） | 开发中 |
| M06.F03.I02 | 创建参数 | 接口 | 前端+后端 | POST /api/inspection/parameters：code/name/rawName/canonicalName 必填；sourceType 默认 OFFICIAL；aliases 默认 [] | 开发中 |
| M06.F03.I03 | 更新参数 | 接口 | 前端+后端 | PUT /api/inspection/parameters/{code}：PATCH 语义；aliases 传则整体替换 | 开发中 |
| M06.F03.I04 | 删除参数 | 接口 | 前端+后端 | DELETE /api/inspection/parameters/{code}：204 if exists | 开发中 |
| M06.F03.I05 | 标准↔参数 link | 接口 | 前端+后端 | POST /api/inspection/links/standard-parameter：建立 standard→parameter 关联 | 开发中 |
| M06.F03.I06 | 标准↔参数 unlink | 接口 | 前端+后端 | DELETE /api/inspection/links/standard-parameter：404 if 不存在 | 开发中 |
| M06.F03.I07 | 参数↔界面 unlink | 接口 | 前端+后端 | DELETE /api/param-interfaces/links：404 if 不存在 | 开发中 |
| M06.F03.I08 | 标准↔参数 列表 | 接口 | 前端+后端 | GET /api/inspection/links/standard-parameter?inspectionStandardCode=&inspectionParameterCode=：`Page<StandardParameterLink>`，按 standardCode/parameterCode 过滤 | 开发中 |

### M06.F04 检测标准

| 子项 ID | 名称 | 类型 | 交付 | 说明 | 状态 |
|---|---|---|---|---|---|
| M06.F04.I01 | 标准列表 | 接口 | 前端+后端 | GET /api/inspection/standards?page=&pageSize=&keyword=&status=：`Page<InspectionStandard>`，按 code/name 模糊 + status 过滤（active/superseded/draft） | 开发中 |
| M06.F04.I02 | 创建标准 | 接口 | 前端+后端 | POST /api/inspection/standards：code/name 必填；status 默认 ACTIVE | 开发中 |
| M06.F04.I03 | 更新标准 | 接口 | 前端+后端 | PUT /api/inspection/standards/{code}：PATCH 语义 | 开发中 |
| M06.F04.I04 | 删除标准 | 接口 | 前端+后端 | DELETE /api/inspection/standards/{code}：204 if exists | 开发中 |
| M06.F04.I05 | 项目↔报告名称 unlink | 接口 | 前端+后端 | DELETE /api/report-names/links/object：404 if 不存在 | 开发中 |
| M06.F04.I06 | 报告名称↔参数 unlink | 接口 | 前端+后端 | DELETE /api/report-names/links/parameter：404 if 不存在 | 开发中 |
| M06.F04.I07 | 报告名称↔标准 unlink | 接口 | 前端+后端 | DELETE /api/report-names/links/standard：404 if 不存在 | 开发中 |

---

## 维护约定

- 谁改功能，谁改表，同一个 commit。
- `规划` → `开发中`：必须先有需求文档引用它。
- `开发中` → `已上线`：L5 会警告它缺设计映射与测试引用。警告不阻断，由人裁量。
- **I 级登记走 mirror 免批**：`python scripts/tree_change.py -p lab-management-system-django --report` 提案带 `"mirror": true`、`action=新增`，ID 必须已在 shared BASE 树；`--apply` 自查自批（ADR-0042）。
