# 登录状态同步与故障排除极简指南

当 NotebookLM PDF 微服务出现故障（任务状态显示 `failed` 或接口返回 `auth_expired`）时，请按照以下精简步骤完成同步。

## 📁 核心路径清单

- **本地文件路径**：`C:\Users\Mayn\.notebooklm\storage_state.json`
- **服务器正式路径**：`/opt/notebooklm-py/env/storage_state.json`
- **本地项目目录**：`D:\notebooklm-py`

---

## 🚀 第一步：本地重新登录并保存

请在您本地的 `PowerShell` 或 `CMD` 中执行以下命令：

1. **进入项目根目录**：
   ```powershell
   cd D:\notebooklm-py
   ```
2. **运行登录程序**：
   ```powershell
   uv run notebooklm login
   ```
3. **完成验证**：在弹出的浏览器中登录 Google 账号并进入 NotebookLM 首页。
4. **保存状态**：回到终端按下 **ENTER** 键，确保生成最新的加密文件。

---

## 🚀 第二步：将最新状态同步到服务器

在本地终端继续执行 `scp` 命令（将 `<IP>` 替换为您真实的服务器 IP）：

```powershell
scp C:\Users\Mayn\.notebooklm\storage_state.json root@43.160.205.161:/opt/notebooklm-py/env/storage_state.json
```

---

## 🚀 第三步：服务器修正并重启

登录服务器 SSH 后，执行以下三行命令使配置生效：

1. **修正权限与所有者**：
   ```bash
   sudo chown www-data:www-data /opt/notebooklm-py/env/storage_state.json
   sudo chmod 600 /opt/notebooklm-py/env/storage_state.json
   ```
2. **同步给 root 备份（可选）**：
   ```bash
   mkdir -p /root/.notebooklm/
   cp /opt/notebooklm-py/env/storage_state.json /root/.notebooklm/storage_state.json
   ```
3. **重启并验证服务**：
   ```bash
   sudo systemctl restart notebooklm-pdf.service
   curl http://127.0.0.1:8000/healthz
   ```

**✅ 验证标准**：`curl` 返回的结果中 `auth_configured` 必须为 `true`。
