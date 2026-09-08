# Data model

`data/sources.json` 保存当前 Source Registry，包括 `source_id`、显示名、核素、参考数值与单位、位置、holder 和状态。普通放射性源使用 Bq；`source.md` 中的 AmC/AmBe 中子源使用 `n/s`，其原始台账信息保存在每个 Source 的 `ledger` 元数据中。可选状态严格限定为 `in_stock`、`checked_out`、`calibrating`、`acu_in_use`、`cls_in_use`、`inactive`，分别表示在库、借出、刻度中、ACU在用、CLS在用和停用。

台账导入由 `scripts/import_source_ledger.py` 完成。每个 Source 的 `activity.reference_date` 使用 `source.md` 的“记录日期”，当前活度和历史活度都以该日期作为指数衰变的起点。

SQLite 的核心表：

- `source_transactions`：状态和位置变化的不可变事实；
- `calibration_records`：刻度历史，包含 `source_id` 和 `source_label_raw`；
- `import_batches`：文件 SHA256、Sheet 和导入统计；
- `audit_logs`：旧值、新值、用户和 IP；
- `users`、`sessions`：本地账号和过期 session。

Calibration 的 `activity_at_calibration_bq` 是 convenience cache，重新计算仍依赖 Source reference activity、reference date 和核素配置。
