# 微服务更新手册

这份文档用于说明：已经部署到服务器上的 NotebookLM PDF 微服务，后续应该如何更新代码、配置和反向代理。

适用场景：

- 你已经把微服务部署到 Linux 服务器
- 服务已经由 `systemd` 托管
- Nginx 已经反向代理到本机 `127.0.0.1:8000`

## 1. 推荐的更新模式

推荐使用下面这条固定流程：

1. 本地修改代码
2. 推送到你自己的代码仓库
3. 服务器拉取最新代码
4. 重新安装项目
5. 重启微服务
6. 做健康检查

如果只是改配置文件或 Nginx，则不需要每次都拉代码。

## 2. 代码更新

### 2.1 本地提交并推送

在本地项目目录执行：

```bash
git add .
git commit -m "feat(service): update pdf service"
git push
```

说明：

- 服务器应拉取你自己的仓库，而不是你没有推送权限的上游仓库
- 如果服务器不是从你的仓库部署的，请先调整远程仓库来源

### 2.2 服务器拉取最新代码

登录服务器后执行：

```bash
cd /opt/notebooklm-py/app
git pull
```

### 2.3 重新安装项目

激活虚拟环境并重新安装：

```bash
source /opt/notebooklm-py/venv/bin/activate
pip install -e .
```

如果你改了依赖，或者需要浏览器相关能力，也可以执行：

```bash
pip install -e ".[browser]"
```

### 2.4 重启服务

```bash
sudo systemctl restart notebooklm-pdf.service
sudo systemctl status notebooklm-pdf.service
```

### 2.5 验证服务

先做本机健康检查：

```bash
curl http://127.0.0.1/healthz
```

如果需要，再做公网检查：

```bash
curl http://43.160.205.161/healthz
```

如果返回类似下面内容，说明服务可用：

```json
{"ok":true,"queue_length":0,"active_job_id":null,"auth_configured":true}
```

## 3. 仅修改 service.env 时

如果你只是修改了服务配置，例如：

- `NOTEBOOKLM_SERVICE_DOWNLOAD_TTL_SECONDS`
- `NOTEBOOKLM_SERVICE_JOB_RETENTION_SECONDS`
- `NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL`
- `NOTEBOOKLM_SERVICE_DEFAULT_LANGUAGE`
- `NOTEBOOKLM_STORAGE_PATH`

那么不需要 `git pull`，只需要：

```bash
sudo systemctl restart notebooklm-pdf.service
sudo systemctl status notebooklm-pdf.service
```

建议重启后立刻做一次健康检查：

```bash
curl http://127.0.0.1/healthz
```

## 4. 仅修改 Nginx 配置时

如果你改的是 Nginx 配置，例如：

- 域名
- 反代地址
- 上传大小限制
- HTTPS 配置

执行：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

如果 `nginx -t` 报错，不要直接 reload，先修配置。

## 5. 推荐的最小更新命令

如果是常规代码更新，最常用的命令就是下面这几条：

```bash
cd /opt/notebooklm-py/app
git pull
source /opt/notebooklm-py/venv/bin/activate
pip install -e .
sudo systemctl restart notebooklm-pdf.service
```

## 6. 查看运行状态

### 查看服务状态

```bash
sudo systemctl status notebooklm-pdf.service
```

### 查看实时日志

```bash
journalctl -u notebooklm-pdf.service -f
```

### 查看最近日志

```bash
journalctl -u notebooklm-pdf.service -n 100 --no-pager
```

## 7. 常见更新场景

### 场景 1：只改了 Python 代码

执行：

```bash
cd /opt/notebooklm-py/app
git pull
source /opt/notebooklm-py/venv/bin/activate
pip install -e .
sudo systemctl restart notebooklm-pdf.service
```

### 场景 2：改了环境变量

执行：

```bash
nano /opt/notebooklm-py/env/service.env
sudo systemctl restart notebooklm-pdf.service
```

### 场景 3：改了 Nginx

执行：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 场景 4：登录态更新

如果 Google / NotebookLM 登录态过期，需要：

1. 在本地重新执行 `notebooklm login`
2. 重新上传最新的 `storage_state.json`
3. 覆盖服务器上的认证文件
4. 重启服务

例如：

```bash
sudo systemctl restart notebooklm-pdf.service
```

## 8. 更新后的建议检查清单

每次更新后，建议至少确认：

- `systemd` 服务是 `active (running)`
- `/healthz` 返回正常
- `auth_configured` 仍然是 `true`
- Nginx 反代正常
- 公网访问仍然可用
- 上传任务可以正常创建

## 9. 一句话 SOP

后续更新默认按这个顺序操作：

```bash
cd /opt/notebooklm-py/app
git pull
source /opt/notebooklm-py/venv/bin/activate
pip install -e .
sudo systemctl restart notebooklm-pdf.service
curl http://127.0.0.1/healthz
```

如果只是改配置，就跳过 `git pull` 和 `pip install`；如果只是改 Nginx，就执行 `nginx -t` 和 `reload`。
