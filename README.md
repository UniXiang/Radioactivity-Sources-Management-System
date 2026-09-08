# JUNO Calibration Source Management System (JCSMS) V1

JCSMS 是面向 JUNO 实验现场局域网的放射源与刻度历史管理系统。当前 Source Registry 只由 `data/sources.json` authoritative 保存；SQLite 只保存刻度记录、状态事务、审计、导入批次和用户 session，避免出现两个 current state 数据源。

## 安装与初始化

需要 Linux、Python 3.11+ 和 Node.js 18+（前端构建时）。推荐创建虚拟环境并安装后端依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
```

也可以在刚 clone 的目录中直接运行一次：

```bash
./setup.sh
```

该脚本会创建 `.venv`、安装 Python/Node 依赖并构建前端；随后按下面的命令创建管理员并启动服务。

初始化目录和 SQLite schema，然后创建第一个管理员：

```bash
python scripts/init_admin.py

# 导入当前放射源台账
PYTHONPATH=backend python scripts/import_source_ledger.py
```

正式使用前，把实际台账写入 `data/sources.json`。`data/sources.example.json` 只用于参考，不会自动写入正式台账。

为避免把现场运行数据提交到代码仓库，`data/sources.json`、SQLite 数据库、导入文件、日志和原始台账文件默认被 `.gitignore` 排除；首次 clone 后应用会自动创建空的数据目录和数据库。

## 启动与访问

```bash
./start.sh
```

默认访问 `http://服务器地址:8080/`。配置位于 `config/config.yaml`，可以通过 `JCSMS_CONFIG` 指定配置文件。所有前端资源构建后从本地 `frontend/dist` 提供，运行时不依赖公网 CDN。

需要临时从公网查看时运行：

```bash
./start_public.sh
```

脚本会启动本地服务并创建一个新的 Cloudflare 临时 HTTPS 地址，地址会打印在终端中。Quick Tunnel 停止后地址失效；重复运行脚本即可再次使用。需要固定域名时，应配置 Cloudflare named tunnel 和自己的域名。

未登录访问会进入匿名 `viewer` 模式，可查看总览、Source、活度、刻度历史和 CSV 导出。借出、归还、刻度、Source 修改、用户管理、审计和导入仍需登录并通过角色权限校验。页面中的“管理登录”可切换到本地账号登录。

Source 状态包括：在库、借出、刻度中、ACU在用、CLS在用和停用。操作员或管理员可以从 Source 详情页标记 ACU/CLS 在用，并在使用结束后恢复为在库。

开发前端时可以分别运行 `npm --prefix frontend run dev` 和 `./start.sh`；Vite 会把 `/api` 代理到 8080。

## 数据与安全边界

- `source_id` 创建后不能修改；Source 不做物理删除，只能停用或恢复。
- 所有 JSON Registry 写入集中经过 `SourceJsonRepository`，使用文件锁、临时文件、flush/fsync、atomic rename，并在覆盖前生成备份。
- 放射性活度以 Bq 保存；台账中的 AmC/AmBe 中子源保留 `n/s` 发射率。后端 `ActivityService` 根据 `config/isotopes.json` 和 Source 的记录日期计算当前或历史数值。
- 状态改变必须经过 checkout、return、calibration start/end、deactivate、reactivate API，并写入 transaction 和 audit log。
- Calibration record 使用 soft delete；XLSX 每行的完整原始数据保存在 `raw_data_json`。
- 密码只保存 bcrypt hash，登录使用 HttpOnly session cookie。

## XLSX 导入

管理员进入 `/import`，上传 XLSX，选择 Sheet，调整字段映射，先验证再确认导入。系统显示文件 SHA256、表头、前 20 行、日期错误、未匹配 Source、重复行，并默认以 `import_batches.sha256` 阻止同一文件重复导入。管理员通过确认 API 的 `duplicate_policy: "reimport"` 可以显式重新导入。未匹配历史记录仍会导入，`source_id` 保持 NULL，原始标签保存在 `source_label_raw`。

## 备份与恢复

手动备份：

```bash
python scripts/backup.py
```

恢复由服务器管理员执行，脚本会先保留当前文件：

```bash
python scripts/restore.py \
  --sources data/backups/sources/sources_YYYYMMDD_HHMMSS.json \
  --database data/backups/database/juno_sources_YYYYMMDD_HHMMSS.db
```

建议将 `scripts/backup.py` 配置到每日 cron 或 systemd timer。SQLite 也会使用 WAL 模式，并在 `data/backups/database/` 保存快照。

## 测试

```bash
PYTHONPATH=backend pytest -q
```

重点覆盖活度半衰期、JSON 原子更新与损坏保护、状态事务、XLSX 日期/空行/未匹配/重复、多 Sheet、权限和服务器重启后的持久化。

## 生产部署

`deployment/juno-source.service` 是 systemd 示例，`deployment/nginx.conf` 是反向代理示例。生产环境应让应用用户拥有项目目录、`data/` 和 `logs/` 的写权限，并限制备份目录的访问权限。
