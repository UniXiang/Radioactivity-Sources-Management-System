# Architecture

JCSMS V1 使用单体 FastAPI 后端和本地打包的 React/Vite 前端。后端分成 API、service、repository 和 SQLite database 层。

`SourceJsonRepository` 是 Source Registry 的唯一读写入口。它在同一个锁内读取、校验、备份、写临时文件、flush/fsync、atomic rename。SQLite 不复制 Source 当前状态，只保存状态变化的事实记录和业务历史。

```text
Browser
  -> FastAPI /api/v1
     -> services
        -> SourceJsonRepository -> data/sources.json
        -> SQLite Database       -> data/database/juno_sources.db
        -> ActivityService       -> config/isotopes.json
```

所有重要修改在 SQLite 中写 `audit_logs`；状态变化额外写 `source_transactions`。跨文件的状态操作先完成受保护的 Registry 更新，再在同一业务操作中写历史事实，服务日志记录异常。

