# XLSX import

上传流程是 preview → mapping → validation → confirm。preview 保存临时上传 token、文件名、大小、SHA256、Sheet 列表、表头和前 20 行；validation 逐行保留完整 raw data，检查日期、Source 匹配、空行和重复行；confirm 创建 `import_batches` 并写入 `calibration_records`。

日期错误是 error，行不会导入；未匹配 Source 是 warning，行仍会导入并保留 `source_id = NULL`。Run Number 使用 TEXT，支持 `12345-12350`、`12345,12346` 和 `run12345`。相同 SHA256 的文件默认拒绝再次导入。

