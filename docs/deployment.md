# Deployment

1. 将项目部署到 Linux 服务器，并创建专用 `jcsms` 用户。
2. 创建 Python virtualenv，安装 `backend/requirements.txt`，构建 `frontend/dist`。
3. 运行 `python scripts/init_admin.py` 创建管理员。
4. 按实际服务器路径修改 `deployment/juno-source.service`，复制到 systemd 后执行 `systemctl enable --now juno-source`。
5. 按实际 hostname 修改 `deployment/nginx.conf`，启用 Nginx 站点。
6. 每日执行 `python scripts/backup.py`。

应用监听内网地址，生产部署建议通过 Nginx 访问。配置文件中的路径均可配置，服务器必须保证 `data/` 和 `logs/` 可写。

