# design-function-map（REQ-2026-030 首切片 + REQ-2026-035 T2 auth 域 / T3 检测字典域）

| 功能 ID | 端点（契约 SSOT） | 接口/表 | 说明 |
|---|---|---|---|
| M02.F01.I01 | GET /api/contracts?keyword=&status=&page=&pageSize= | contracts 表（managed=False） | 租户收口 + 2 过滤 + 1-based 分页切片（默认 1/20），Page 信封 |
| M02.F01.I02 | GET /api/contracts/{id} | contracts | 404 `{code:"NOT_FOUND"}` if 不存在/非本租户 |
| M02.F01.I03 | POST /api/contracts | contracts | 必填 6 项 400（BAD_REQUEST）；id/created_at 应用侧生成；tenant_id 取 claim；201 |
| M02.F01.I04 | PUT /api/contracts/{id} | contracts | 局部合并（Object.assign 语义）；404 if 不存在 |
| M02.F01.I05 | DELETE /api/contracts/{id} | contracts | 204；重复删 404 |
| M00.F01.I01 | GET /api/auth/me | directory/membership jsonb 聚合 | decode-only 会话回显（无租户收口要求） |
| M00.F02.I01 | POST /api/auth/switch-tenant | JWT 重签 | 校验租户归属后换发带 tenant_id claim 的 token |
| M01.F04.I01 | GET /api/auth/menus | 静态树 | 5 根节点导航树（镜像 lab-msw） |
| M01.F04.I02 | GET /api/auth/permissions | 静态权限串 | admin 全量 11 项 |
| M01.F05.I04 | POST /api/auth/refresh | JWT 重签 | 内嵌 saas refresh token 续期 |
| M01.F05.I05 | POST /api/auth/logout | 无状态 | 服务端无 session，204 |
| M01.F05.I06 | POST /api/auth/login + /api/auth/native-login | JWT 重签（代理 saas IdP） | 账密调 saas /api/v1/auth/login（clientId=lab-management），lab JWT 重签（REQ-2026-023 方案 A）；I01 已废弃 |
| M01.F05.I02 | GET /api/auth/sso/authorize | saas forward | RFC 6749 §10.12 state 前端生成原样透传 |
| M01.F05.I03 | POST /api/auth/sso/callback | directory upsert + JWT 重签 | code 换 token + whoami/tenants，首登按 email upsert |
| M06.F01.I01-I07 | /api/inspection/specialties(±/{code}) + links/object-standard | inspection_specialties / object_standard_links | 专项 CRUD + 项目↔标准 junction（role 入 PK） |
| M06.F02.I01-I10 | /api/inspection/objects(±/{code}) + links/specialty-object + links/object-parameter | inspection_objects / specialty_object_links / object_parameter_links | 项目 CRUD + 两 junction（object-parameter 的 qualification_level 入 PK、默认 QUALIFIED） |
| M06.F03.I01-I06, I08 | /api/inspection/parameters(±/{code}) + links/standard-parameter | inspection_parameters / standard_parameter_links | 参数 CRUD（aliases jsonb）+ 标准↔参数 junction（纯键 PK） |
| M06.F04.I01-I04 | /api/inspection/standards(±/{code}) | inspection_standards | 标准 CRUD（status: active/superseded/draft，默认 ACTIVE） |
| M04.F06-F09.I01-I04 | /api/catalog/{models,specs,grades,brands}(±/{code}) | inspection_models/specs/grades/brands | 码表 4 实体同构 CRUD（16 op）：tenant 收口（claim 优先缺省 directory 默认租户 TENANT-001）、create=merge 全覆写（createdAt 刷新）、update=PATCH、回显域分页（items 全量，(sort_order, code) 排序）、他人租户行 404 境外不可见、DELETE miss 404 |

| M03.F01-F08（接样单域 14 op） | /api/receipts(±/{id}±/{id}/history) + task + 七段 act | sample_receipts | rails 镜像（report_flow_service/sample_receipt_service 逐条）：tenant 收口、create=「R-<uuid>」+ flow_status=receiving + contract FK 校验 404、update=PATCH（LIST_FIELDS 跳 None + jsonb 三字段非 None 即 Array(v||[]) 标量包单元素数组）、list 回显信封（page??1/pageSize??20/total=len，updated_at desc + commission_code asc）、5.57 三态 filter、七段 act（operator 整批 400 先校验、per-id err 不整批 5xx、archived 仅 submit 自转移 audit、submit 写/withdraw 清/return 保留 lastSubmittedBy、history entry action/from/to/operator/reason/at）、DTO NON_NULL 递归（render_camel 镜像）、jsonb 键恒在（空时 []） |

| M03.F03.I01-I05 + M03.F01.I07（样品 6 op） | /api/samples(±/{id}±/{id}/ext) | samples | rails SampleService 镜像：tenant 收口 + receipt FK 显式校验（miss→404 "Receipt not found"，不 FK→400）、keyword lower contains sample_code/sample_name、order created_at desc + sample_code asc、create=「S-<uuid>」+ ext 默认 {}、update=PATCH 跳 None（ext 非 None 才替换）、PUT /{id}/ext=整体替换且 ext 必填 400（5.89）、delete 204、DTO NON_NULL（ext 键恒在空 {}） |

| M03.F03.I06-I11（检测记录 6 op） | /api/test-records(±/{id}) + /{id}/verdict | test_records | rails TestRecordService 镜像：tenant 收口、create 四必填 400（sampleId/parameterCode/requirement/result，rails 字面量）+ sample/parameter/standard FK 走 DB 约束（IntegrityError→400，savepoint 包裹防事务污染）、order updated_at desc + id asc、update=PATCH 跳 None、PATCH /{id}/verdict 直写可置 null（NON_NULL→键不在）、id=「TR-<uuid>」 |

| M06.F08.I01-I06 + M06.F03.I07（参数界面 8 op） | /api/param-interfaces(±/{code}) + /links(POST/DELETE/GET) | inspection_param_interfaces + links | rails ParamInterfaceService/Junctions 镜像：平台级字典无 tenant（decode-only 无租户收口）、create code+componentPath 必填 400 + sortOrder 默认 0、list keyword code/name + order (sort_order, code)、回显信封 pageSize 缺省=len(items)、delete miss 404、config 非 dict 回退 {}、junction 复用 upsert_junction/unlink_junction（link 恒 204 upsert 整行覆盖含 created_at；unlink 幂等 no-op 204）；GET links 为契约豁免辅助端点不挂 ID |

| M06.F07.I01-I08 + M06.F04.I05-I07（报告名称 14 op） | /api/report-names(±/{code}) + /links/{object,standard,parameter} | inspection_report_names + 3 junction 表 | rails InspectionReportNameService/ReportNameJunctions 镜像：create code+name 必填 400 + **JPA merge**（同 code 覆盖整行含 createdAt，2026-09-29 live 共库对拍实锤）、extFields 非 list 回退 []、字典信封 pageSize 缺省=len、junction 三组（standard 组 role 入 PK，同 standard 不同 role 并存）link upsert 恒 204 / unlink 幂等 no-op 204 / GET 短信封 page=1（三组 GET 豁免不挂 ID） |

| M06.F06.I01-I05（技术要求 5 op） | /api/technical-requirements(±/{object}/{param}/{standard}) | inspection_technical_requirements | rails TechnicalRequirementService/Fields 镜像：tenant 收口（claim 优先缺省 directory 默认租户）、list 4 过滤 + order (sort_order, object, parameter, standard) **裸数组**、create 三键任一缺失 400 + **JPA merge**（同三键+同租户覆盖整行含 createdAt）+ 枚举缺省 valueType=numeric/comparison=≥/judgmentMode=manual/verificationStatus=draft（`body[k] \|\| default`）+ NULLABLE 15 键直透 + sortOrder 默认 0、update 全字段跳 None + updated_at 恒刷、delete/get 他人租户行 miss→404 境外不可见、DTO NON_NULL 剔 None |
| M06.F05.I01-I05（计算方法 5 op） | /api/calculation-methods(±/{object}/{param}) | inspection_calculation_methods | rails CalculationMethodService 镜像：平台级字典无 tenant（decode-only）、list 双过滤 + order (sort_order, object, parameter) **裸数组**（rails 分叉，非字典信封）、create 双键任一缺失 400 + **JPA merge**（同双键覆盖整行含 createdAt）+ 缺省 algorithmType=manual/specimenCount=1/sortOrder=0、update truthy/strict 双判定（镜像 springboot mapper：truthy 真值才写、strict 非 None 即写——specimenCount/sortOrder 可写 0）、delete miss→404、DTO NON_NULL 剔 None | |

## 与 saas 首切片的关键语义分叉（防跨家族串味）

- 分页：lab **1-based 切片**（CT T11 仲裁）；saas 0 基——分页语义分叉在案
- 鉴权：decode-only 不验签 + `UNAUTHORIZED` 信封；saas-django 是 HS256 验签 + DRF 401
- 列形：lab contracts 全 text（时间戳/主键无 DB 默认，应用侧生成）；saas tenant 表是 uuid/timestamptz + db_default
- status：lab 直存字符串 active/archived；saas smallint 1/2 映射
- 错误体：两家族同形 `{code,message}`（NOT_FOUND / BAD_REQUEST / UNAUTHORIZED）
- 字典域鉴权：M06 检测字典域为平台级实体（无 tenant 列）→ decode-only bearer **无租户收口**，401 `INVALID_CREDENTIALS "Bearer token required"`；contracts 域 BearerAuthentication 需 tenant_id claim + `UNAUTHORIZED` 信封——**两个鉴权面并存**，勿串
- 字典域分页：无切片回显信封（items=全量过滤结果，page/pageSize 纯回显），按 (sort_order, code) 排序；与 contracts 域 1-based 切片**不同**——共享 op 级定稿表（5.127③）为准
- 参数界面域 pageSize 缺省=len(items)（rails 分叉，勿套 receipts 的 20）；unlink 幂等 no-op 204（rails `&.destroy!` 参照实现；树文本「404 if 不存在」为旧注记不采用，同 act-422 裁定）
- **复合 PK 表禁 row.save()/.delete()**：Django legacy 多 `primary_key=True` 只认首列作 `Meta.pk`，`row.save()` 的 UPDATE WHERE 只按首列会误伤共享首键的兄弟行（T9 实锤：同 object 三行被连环覆写）。TR/CM create-merge/update/delete 一律走 `queryset.filter(全键).update/delete/create`，junction upsert 同收（helpers.upsert_junction 已改 query.update 路径——T7/T8 已落地 junction 的 update 路径带同款隐患，本批一并闭合）
- 技术要求/计算方法 list 均**裸数组**（rails render_camel 直出，非字典信封）；CM update truthy/strict 双判定（truthy 真值才写、strict 非 None 即写，specimenCount/sortOrder 可写 0）
- 汇总域：/api/summary 回显 summaryName/columns(6 固定)/rows（nil→"" to_s 镜像，dateFrom/dateTo 走 commission_date 字典序）；/api/summary/stats **wire 键直出不走 camel**（funnelByStage 的 pending_collect 是 openapi 生成名，不得折叠成 pendingCollect）；「今天」与 created_at 同钟取 UTC（rails 2026-10-21 SummaryApiTest 实证红镜像）；qualifiedRateByMaterial 码表 summaryName 关键词归类 concrete/rebar/sand，rate 三位小数半入
- _frontend-bind/snapshot：生成器 DTO 占位端点（rails/go 同款裁定）——挂认证，登录后 404 NOT_FOUND、匿名 401；**永久不接**，501/404 即符合契约
