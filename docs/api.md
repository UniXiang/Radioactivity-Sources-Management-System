# API

API prefix 为 `/api/v1`，健康检查为公开的 `GET /health`。除登录接口外，接口需要 `jcsms_session` HttpOnly cookie。

主要接口：

| Method | Path | Role |
|---|---|---|
| GET | `/sources` | viewer |
| POST | `/sources` | admin |
| PATCH | `/sources/{source_id}` | admin |
| GET | `/sources/{source_id}/activity` | viewer |
| POST | `/sources/{source_id}/checkout` | operator/admin |
| POST | `/sources/{source_id}/return` | operator/admin |
| POST | `/sources/{source_id}/acu/start` | operator/admin |
| POST | `/sources/{source_id}/acu/end` | operator/admin |
| POST | `/sources/{source_id}/cls/start` | operator/admin |
| POST | `/sources/{source_id}/cls/end` | operator/admin |
| POST | `/sources/{source_id}/calibration/start` | operator/admin |
| POST | `/sources/{source_id}/calibration/end` | operator/admin |
| GET/POST/PATCH | `/calibrations...` | viewer/operator/admin |
| POST | `/import/xlsx/preview` | admin |
| POST | `/import/xlsx/validate` | admin |
| POST | `/import/xlsx/confirm` | admin |
| GET | `/audit` | admin |

错误响应使用 `error.code` 和 `error.message`；登录依赖缺失时为 401，权限不足时为 403，Source 不存在时为 `SOURCE_NOT_FOUND`。
