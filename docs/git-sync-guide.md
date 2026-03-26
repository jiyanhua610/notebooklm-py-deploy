# Git 同步指南：拉取原作者仓库的最新变更

这份文档适用于当前仓库这种场景：

- 你本地克隆了一个 GitHub 项目
- 你自己也有一个仓库副本
- 原作者仓库还在持续更新
- 你想把原作者的新代码同步到自己本地，必要时再推送到自己的仓库

## 1. 先理解当前远程配置

你当前仓库的远程配置如下：

```bash
git remote -v
```

示例：

```text
myorigin  https://github.com/jiyanhua610/notebooklm-py-deploy.git (fetch)
myorigin  https://github.com/jiyanhua610/notebooklm-py-deploy.git (push)
origin    https://github.com/teng-lin/notebooklm-py.git (fetch)
origin    https://github.com/teng-lin/notebooklm-py.git (push)
```

这代表：

- `origin`：原作者仓库
- `myorigin`：你自己的仓库

所以，想同步原作者最新代码时，应该从 `origin` 拉取。

## 2. 最常用的同步方式

先检查当前工作区是否干净：

```bash
git status
```

再查看当前所在分支：

```bash
git branch --show-current
```

如果你当前就在主分支，例如 `main`，可以直接执行：

```bash
git fetch origin
git pull origin main
```

如果原作者默认分支不是 `main`，而是 `master`，就改成：

```bash
git fetch origin
git pull origin master
```

## 3. 更稳妥的推荐流程

如果你平时会切不同分支开发，建议按下面顺序操作：

### 步骤 1：先确认本地有没有未提交修改

```bash
git status
```

如果看到有未提交内容，建议先：

- 提交到本地分支
- 或使用 `git stash` 暂存

否则 `git pull` 时可能出现冲突。

### 步骤 2：切到你要同步的主分支

通常是：

```bash
git checkout main
```

如果你的主分支叫 `master`：

```bash
git checkout master
```

### 步骤 3：拉取原作者最新代码

```bash
git fetch origin
git pull origin main
```

### 步骤 4：如果需要，再同步到你自己的 GitHub 仓库

```bash
git push myorigin main
```

这样你本地和你自己的远程仓库都会跟上原作者最新版本。

## 4. 推荐你现在直接用的命令

基于你当前仓库配置，最常见的一组命令是：

```bash
git status
git checkout main
git fetch origin
git pull origin main
git push myorigin main
```

如果你的主分支不是 `main`，请把命令里的 `main` 替换成实际分支名。

## 5. 如果不确定默认分支叫什么

可以先看本地分支：

```bash
git branch
```

也可以看远程分支：

```bash
git branch -r
```

常见结果会包含：

- `origin/main`
- `origin/master`

看到哪个，就优先拉哪个。

## 6. 如果拉取时报冲突怎么办

常见原因：

- 你本地改过同一段代码
- 原作者也改了同一段代码

这时 Git 会提示冲突文件，你需要：

1. 打开冲突文件
2. 手动决定保留哪部分内容
3. 保存后执行：

```bash
git add .
git commit -m "merge origin main"
```

如果你不想现在处理冲突，先不要继续推送，先把冲突解决干净。

## 7. 如果本地有修改，但又想先拉最新代码

可以先暂存：

```bash
git stash
git pull origin main
git stash pop
```

说明：

- `git stash`：先把当前未提交修改收起来
- `git stash pop`：拉完最新代码后再恢复

如果恢复时有冲突，还是需要手动处理。

## 8. `fetch` 和 `pull` 的区别

很多同学会混淆这两个命令：

- `git fetch origin`
  只是把远程最新提交拉到本地，不会自动合并

- `git pull origin main`
  等于“先拉取，再合并”

如果你想更稳一点，可以用两步：

```bash
git fetch origin
git merge origin/main
```

## 9. 当前仓库最适合的远程使用习惯

结合你现在的配置，建议长期保持下面这个习惯：

- `origin`：始终指向原作者仓库
- `myorigin`：始终指向你自己的仓库

这样分工很清楚：

- 从原作者更新：`pull/fetch origin`
- 推送到自己仓库：`push myorigin`

## 10. 一份最简操作卡片

只想记最核心的几条，可以直接记这个：

```bash
git status
git checkout main
git fetch origin
git pull origin main
git push myorigin main
```

## 11. 什么时候不建议直接拉

下面几种情况，建议先停一下再操作：

- 你本地有很多未提交修改
- 你当前不在主分支
- 你不确定原作者默认分支是不是 `main`
- 你准备上线，担心直接同步会影响当前运行版本

这时建议先做备份分支：

```bash
git checkout -b backup-before-sync
```

然后再同步，会更稳妥。
