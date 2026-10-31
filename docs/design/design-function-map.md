# design-function-map（REQ-2026-029 首切片）

| 功能 ID | 端点（契约 SSOT） | 接口/表 | 说明 |
|---|---|---|---|
| M02.F01.I01 | GET /api/contracts?keyword=&status=&page=&pageSize= | contracts 表（managed=False） | 租户收口 + 2 过滤 + 1-based 分页切片（默认 1/20），Page 信封 |
| M02.F01.I02 | GET /api/contracts/{id} | contracts | 404 `{code:"NOT_FOUND"}` if 不存在/非本租户 |
| M02.F01.I03 | POST /api/contracts | contracts | 必填 6 项 400（BAD_REQUEST）；id/created_at 应用侧生成；tenant_id 取 claim；201 |
| M02.F01.I04 | PUT /api/contracts/{id} | contracts | 局部合并（Object.assign 语义）；404 if 不存在 |
| M02.F01.I05 | DELETE /api/contracts/{id} | contracts | 204；重复删 404 |

## 与 saas 首切片的关键语义分叉（防跨家族串味）

- 分页：lab **1-based 切片**（CT T11 仲裁）；saas 0 基——分页语义分叉在案
- 鉴权：decode-only 不验签 + `UNAUTHORIZED` 信封；saas-django 是 HS256 验签 + DRF 401
- 列形：lab contracts 全 text（时间戳/主键无 DB 默认，应用侧生成）；saas tenant 表是 uuid/timestamptz + db_default
- status：lab 直存字符串 active/archived；saas smallint 1/2 映射
- 错误体：两家族同形 `{code,message}`（NOT_FOUND / BAD_REQUEST / UNAUTHORIZED）
