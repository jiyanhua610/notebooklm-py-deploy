# 部署手册：如何部署到一台独立服务器

这份文档讲的是最实用的一种部署方式：把 NotebookLM PDF 微服务部署到一台独立服务器上，供你的 SaaS 内部调用。

目标是：

- 一台服务器
- 一个 Redis
- 一个长期可维护的 NotebookLM 登录态
- 一个常驻运行的 FastAPI 服务
- SaaS 通过 HTTP 调用它

## 1. 先理解这台服务器上会跑什么

在独立服务器上，最少需要这些组件：

1. `notebooklm-py` 代码和 Python 环境
2. Redis
3. NotebookLM PDF 服务进程
4. 一个反向代理，可选但推荐，比如 Nginx
5. 一份有效的 NotebookLM 认证信息

服务的执行模式是：

- 用户请求进来后进入 Redis 队列
- 同一时刻只执行 1 个 NotebookLM 任务
- 后续任务排队等待
- 结果 PDF 先保存在服务本机
- 服务返回临时下载 URL

## 2. 推荐的服务器规格

第一版推荐比较保守：

- 2 vCPU
- 4 GB 内存
- 20 GB 以上磁盘
- Linux 64 位
- 能访问 `notebooklm.google.com`

如果你后续排队任务很多，磁盘要适当加大，因为排队时多个源文件会先落本地。

## 3. 推荐的目录结构

假设你把服务部署到：

```text
/opt/notebooklm-py
```

建议目录结构：

```text
/opt/notebooklm-py/
├── app/                  # 代码目录
├── venv/                 # Python 虚拟环境
├── runtime/
│   ├── tmp/              # 上传临时文件
│   └── downloads/        # 结果 PDF
├── env/
│   └── service.env       # 环境变量文件
└── logs/                 # 可选日志目录
```

## 4. 安装系统依赖

以 Ubuntu / Debian 为例：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip redis-server nginx
```

确认 Redis 已启动：

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
sudo systemctl status redis-server
```

## 5. 部署代码

```bash
sudo mkdir -p /opt/notebooklm-py
sudo chown $USER:$USER /opt/notebooklm-py
cd /opt/notebooklm-py

git clone <你的仓库地址> app
cd app
```

## 6. 创建 Python 虚拟环境

```bash
cd /opt/notebooklm-py
python3 -m venv venv
source venv/bin/activate
```

安装依赖：

```bash
cd /opt/notebooklm-py/app
pip install -e ".[service,browser]"
```

如果你还想在服务器上跑测试或调试：

```bash
pip install -e ".[service,browser,dev]"
```

## 7. 最关键的一步：准备 NotebookLM 登录态

### 7.1 不建议在无头服务器上直接登录

这个项目底层依赖 Google 浏览器登录态。通常更稳的做法是：

1. 在你自己的本地电脑上执行 `notebooklm login`
2. 拿到 `storage_state.json`
3. 拷贝到服务器

### 7.2 在本地生成登录态

```bash
notebooklm login
```

成功后得到：

```text
~/.notebooklm/storage_state.json
```

### 7.3 拷贝到服务器

你可以复制成一个单独文件，比如：

```bash
scp C:\Users\Mayn\.notebooklm\storage_state.json root@43.160.205.161:/opt/notebooklm-py/env/storage_state.json
```

### 7.4 安全建议

这个文件本质上是登录态凭证，要按密钥来保护：

```bash
chmod 600 /opt/notebooklm-py/env/storage_state.json
```

不要把它提交到 Git。
不要发到群里。
不要放到公开文件服务器。

## 8. 配置环境变量

新建环境变量文件：

```bash
mkdir -p /opt/notebooklm-py/env
nano /opt/notebooklm-py/env/service.env
```

建议内容如下：

```bash
NOTEBOOKLM_SERVICE_API_TOKEN=replace-with-a-long-random-secret
NOTEBOOKLM_SERVICE_REDIS_URL=redis://127.0.0.1:6379/0
NOTEBOOKLM_SERVICE_QUEUE=notebooklm:pdf:queue
NOTEBOOKLM_SERVICE_PREFIX=notebooklm:pdf
NOTEBOOKLM_SERVICE_TMP_DIR=/opt/notebooklm-py/runtime/tmp
NOTEBOOKLM_SERVICE_DOWNLOADS_DIR=/opt/notebooklm-py/runtime/downloads
NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE=20
NOTEBOOKLM_SERVICE_DOWNLOAD_TTL_SECONDS=3600
NOTEBOOKLM_SERVICE_QUEUE_TIMEOUT_SECONDS=14400
NOTEBOOKLM_SERVICE_SOURCE_WAIT_TIMEOUT_SECONDS=300
NOTEBOOKLM_SERVICE_GENERATION_WAIT_TIMEOUT_SECONDS=1800
NOTEBOOKLM_SERVICE_RETRY_ATTEMPTS=2
NOTEBOOKLM_SERVICE_RETRY_DELAY_SECONDS=2
NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL=http://43.160.205.161:8000
NOTEBOOKLM_STORAGE_PATH=/opt/notebooklm-py/env/storage_state.json
```

### 8.1 参数说明

- `NOTEBOOKLM_SERVICE_API_TOKEN`
  SaaS 调用服务时要带的固定令牌
- `NOTEBOOKLM_SERVICE_REDIS_URL`
  Redis 地址
- `NOTEBOOKLM_SERVICE_TMP_DIR`
  上传文件临时目录
- `NOTEBOOKLM_SERVICE_DOWNLOADS_DIR`
  结果 PDF 存放目录
- `NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE`
  最大排队数量，包含执行中的任务和待执行任务
- `NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL`
  返回给 SaaS 的下载地址前缀
- `NOTEBOOKLM_STORAGE_PATH`
  NotebookLM 登录态文件路径

## 9. 创建运行目录

```bash
mkdir -p /opt/notebooklm-py/runtime/tmp
mkdir -p /opt/notebooklm-py/runtime/downloads
```

## 10. 先手动启动一次验证

```bash
cd /opt/notebooklm-py/app
source /opt/notebooklm-py/venv/bin/activate
set -a
source /opt/notebooklm-py/env/service.env
set +a
notebooklm-pdf-service
```

如果你不用项目脚本，也可以：

```bash
uvicorn notebooklm.service.app:create_app --factory --host 0.0.0.0 --port 8000
```

### 10.1 验证健康检查

```bash
curl http://127.0.0.1:8000/healthz
```

应该看到：

```json
{
  "ok": true,
  "queue_length": 0,
  "active_job_id": null,
  "auth_configured": true
}
```

如果 `auth_configured` 是 `false`，先不要往下部署，先解决认证文件问题。

## 11. 配置 systemd 守护进程

创建服务文件：

```bash
sudo nano /etc/systemd/system/notebooklm-pdf.service
```

写入下面内容：

```ini
[Unit]
Description=NotebookLM PDF Service
After=network.target redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/notebooklm-py/app
EnvironmentFile=/opt/notebooklm-py/env/service.env
ExecStart=/opt/notebooklm-py/venv/bin/uvicorn notebooklm.service.app:create_app --factory --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

注意：

- 如果你不用 `www-data`，改成你自己的部署用户
- `WorkingDirectory`、`EnvironmentFile`、`ExecStart` 路径要跟你的真实路径一致

### 11.1 修正目录权限

```bash
sudo chown -R www-data:www-data /opt/notebooklm-py/runtime
sudo chown www-data:www-data /opt/notebooklm-py/env/storage_state.json
sudo chmod 600 /opt/notebooklm-py/env/storage_state.json
```

### 11.2 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable notebooklm-pdf.service
sudo systemctl start notebooklm-pdf.service
sudo systemctl status notebooklm-pdf.service
```

查看日志：

```bash
journalctl -u notebooklm-pdf.service -f
```

## 12. 配置 Nginx

创建站点配置：

```bash
sudo nano /etc/nginx/sites-available/notebooklm-pdf
```

示例配置：

```nginx
server {
    listen 80;
    server_name your-pdf-service.example.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/notebooklm-pdf /etc/nginx/sites-enabled/notebooklm-pdf
sudo nginx -t
sudo systemctl reload nginx
```

## 13. 建议加 HTTPS

如果服务器对内外都可访问，建议至少给域名加 HTTPS。常见做法是使用 Certbot：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-pdf-service.example.com
```

## 14. 部署后怎么验收

### 14.1 健康检查

```bash
curl https://your-pdf-service.example.com/healthz
```

### 14.2 提交测试任务

```bash
curl -X POST "https://your-pdf-service.example.com/v1/pdf-jobs" \
  -H "X-API-Token: replace-with-a-long-random-secret" \
  -F "files=@example.pdf" \
  -F "files=@appendix.docx" \
  -F "title=服务器联调测试" \
  -F "instructions=请基于全部材料输出适合汇报的中文 PDF"
```

### 14.3 查询任务状态

```bash
curl "https://your-pdf-service.example.com/v1/pdf-jobs/<job_id>" \
  -H "X-API-Token: replace-with-a-long-random-secret"
```

### 14.4 下载文件

成功后拿 `download_url` 直接下载。当前结果文件为 `.pdf`。

## 15. 生产维护建议

### 15.1 重点监控这几个问题

1. Redis 是否可用
2. `/healthz` 是否正常
3. `queue_length` 是否长期过大
4. 是否频繁出现 `auth_expired`
5. 磁盘是否被 `tmp/` 或 `downloads/` 占满

### 15.2 最常见的运维故障

#### 认证失效

现象：

- 任务不断失败
- `error_code = auth_expired`

处理方法：

1. 在本地重新执行 `notebooklm login`
2. 重新上传新的 `storage_state.json`
3. 重启服务

**详细步骤请参考：[登录同步指南](file:///d:/notebooklm-py/docs/login-sync-guide.md)**

```bash
sudo systemctl restart notebooklm-pdf.service
```

#### 队列堆积过多

现象：

- `queue_length` 很大
- 用户等待时间很长

处理方式：

1. 先确认是不是 NotebookLM 本身响应变慢
2. 考虑调小文件大小或限制提交频率
3. 适当调整 `MAX_QUEUE_SIZE`
4. 不建议在第一版直接改成多并发执行

#### 磁盘占满

重点检查：

- `/opt/notebooklm-py/runtime/tmp`
- `/opt/notebooklm-py/runtime/downloads`

## 16. 回滚方案

如果新版本部署后有问题，最简单的回滚方式是：

1. 切回上一个 Git commit
2. 重新安装依赖
3. 重启 systemd 服务

```bash
cd /opt/notebooklm-py/app
git checkout <上一个可用提交>
source /opt/notebooklm-py/venv/bin/activate
pip install -e ".[service,browser]"
sudo systemctl restart notebooklm-pdf.service
```

## 17. 你上线前至少要确认的清单

上线前请逐项确认：

- Redis 已安装并开机自启
- 服务能正常启动
- `/healthz` 返回 `auth_configured = true`
- 能成功提一个真实多文件任务
- 能拿到 `download_url`
- 下载链接可用且会过期
- systemd 能自动拉起服务
- Nginx 代理正常
- API Token 已经替换成正式强密码
- `storage_state.json` 权限正确且不会泄露

这套流程跑通后，这台服务器就可以作为独立的 NotebookLM PDF 微服务给你的 SaaS 使用。