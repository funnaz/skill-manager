---
name: skill-manager
description: |
  管理本机 Agent Skills：扫描、可视化、创建、安装、依赖检测、冲突检测、健康评分、检测新版本、升级、整合、备份恢复、回收站、禁用、删除、使用统计、导入导出、导出报告。
  触发方式：/skill-manager、/skill管家、「帮我管理 skill」「安装新 skill」「删除无用 skill」「禁用 skill」「导出 skill 报告」「打开 skill 面板」
  Manage local agent skills: scan, visualize, create, install, update, merge, restore backups, disable, delete, usage stats, export.
  Trigger: /skill-manager, "manage my skills", "install a skill", "delete unused skill", "disable skill", "export skill report", "open skill dashboard".
  GitHub: https://github.com/funnaz/skill-manager
metadata:
  short-description: "Manage, update, back up, and report local agent skills"
---

# Skill Manager

帮助用户管理本机 Agent Skills。默认支持 **Grok Build**、**Claude Code**、**OpenAI Codex**、**Cursor**，以及共享目录 `~/.agents/skills/`。

## 何时使用

- 用户想查看电脑里装了哪些 skills、分别挂在哪些 agent 上
- 用户想新建一个 skill 模板
- 用户想从本地目录或 GitHub 安装 skill
- 用户想删除不再使用的 skill，或先预览会删除哪些路径
- 用户想查看备份、恢复整合/升级前的版本
- 用户想查看回收站、撤销误删
- 用户想检查依赖、触发词冲突或健康评分
- 用户想导出/导入 .skillpkg
- 用户想从模板创建或 fork 现有 skill
- 用户想查看本机 skill 使用频率
- 用户想打开可视化面板

## 项目位置

本 skill 自带 CLI 和 Web 面板。优先使用仓库内脚本：

```text
<skill-manager-root>/
  SKILL.md
  cli.py
  server.py
  scanner.py
  manager.py
  static/index.html
  docs/USER_GUIDE.md
  docs/CLI_REFERENCE.md
```

如果用户通过 `~/.grok/skills/skill-manager/` 安装，则 `<skill-manager-root>` 即该目录。

GitHub 仓库：https://github.com/funnaz/skill-manager

用户手册：`docs/USER_GUIDE.md`  
CLI 参考：`docs/CLI_REFERENCE.md`

## 工作流

### 1. 扫描现状

先运行扫描，再向用户汇报摘要：

```bash
python <skill-manager-root>/cli.py scan
```

关注：
- 每个 agent 安装了多少 skills
- 哪些是 Grok 内置 / marketplace / 用户自定义
- 哪些可以删除（`deletable: true`）

### 2. 打开可视化面板

用户需要界面时启动本地服务：

```bash
python <skill-manager-root>/cli.py serve --port 5520
```

然后告诉用户访问 `http://127.0.0.1:5520`。

### 3. 创建新 Skill

收集：
1. `name`：小写字母、数字、连字符
2. `description`：用于自动触发
3. `scope`：
   - `grok` → `~/.grok/skills/<name>/`
   - `agents` → `~/.agents/skills/<name>/`
   - `claude` → `~/.claude/skills/<name>/`
   - `codex` → `~/.codex/skills/<name>/`
   - `cursor` → `~/.cursor/skills/<name>/`

执行：

```bash
python <skill-manager-root>/cli.py create --name <name> --description "<desc>" --scope grok
```

创建后提示用户编辑 `SKILL.md` 正文。

### 4. 安装 Skill

支持两种方式：

**本地目录：**

```bash
python <skill-manager-root>/cli.py install --from-path "C:/path/to/skill" --scope grok
```

**GitHub 仓库：**

```bash
python <skill-manager-root>/cli.py install --git "https://github.com/user/repo.git" --subpath "skills/my-skill" --scope agents
```

安装前检查目标 scope 是否已存在同名 skill；若存在，先问用户是否改名称或删除旧版本。

### 5. 禁用 / 启用 Skill（Grok）

写入 `~/.grok/config.toml` 的 `[skills] disabled` 列表：

```bash
python <skill-manager-root>/cli.py disable --name <skill-name>
python <skill-manager-root>/cli.py enable --name <skill-name>
```

### 6. 删除无用 Skill

只允许删除用户自定义或手动安装的 skills。以下类型**禁止删除**：
- Grok 内置（`grok-bundled`）
- Marketplace 缓存
- 依赖包内置
- `skill-manager` 自身

先确认：

```bash
python <skill-manager-root>/cli.py scan
```

找到目标后，必须让用户明确确认，再执行：

```bash
python <skill-manager-root>/cli.py delete --name <skill-name>
```

删除前可先预览真实路径：

```bash
python <skill-manager-root>/cli.py delete --name <skill-name> --dry-run
```

普通删除默认移入 `~/.skill-manager/trash/`。查看和恢复：

```bash
python <skill-manager-root>/cli.py trash
python <skill-manager-root>/cli.py trash-restore --trash-id <trash-id>
```

如果 skill 在 `~/.agents/skills/`，删除时同步清理相关 junction 桥接，并更新 `~/.agents/.skill-lock.json`。

批量删除：

```bash
python <skill-manager-root>/cli.py delete --batch "old-skill,another-skill"
```

### 7. 检测新版本

```bash
python <skill-manager-root>/cli.py check-updates
python <skill-manager-root>/cli.py check-updates --names "dbs,lark-doc"
python <skill-manager-root>/cli.py check-updates --merge
```

批量升级默认并发 4 个线程，最多 8 个线程：

```bash
python <skill-manager-root>/cli.py batch-upgrade --workers 4
```

检查逻辑：
- **GitHub 源**：拉取仓库并比较 skill 目录内容哈希
- **well-known 源**（如飞书 lark skills）：拉取远程 `SKILL.md`，比较 `version` 与内容哈希
- 状态包括：`up_to_date`、`update_available`、`local_modified`、`content_diff`

### 8. 整合更新（推荐）

当官方有新版本、同时用户本地也改过 skill 时，用整合而不是直接覆盖：

```bash
python <skill-manager-root>/cli.py merge --name lark-doc
```

整合规则：
- 以官方最新版为基础
- 保留本地新增文件
- `SKILL.md`：采用官方 frontmatter + 官方正文，并追加「本地保留内容」
- `references/`、`scripts/` 等官方资源优先采用远程版本
- 操作前自动备份到 `~/.skill-manager/backups/`

### 9. 覆盖升级

GitHub 源可直接覆盖：

```bash
python <skill-manager-root>/cli.py upgrade --name dbs
```

well-known 源若没有本地改动，也会走整合逻辑，仅更新 `SKILL.md`。

检查完成后，应打开 Web 面板的「更新检查报告」弹窗，向用户说明：
1. 哪些 skill 是官方版本号更新
2. 哪些 skill 仅远程内容变化
3. 哪些 skill 本地有改动
4. 每个 skill 的本地文件差异列表

### 10. 导出报告

```bash
python <skill-manager-root>/cli.py export --format markdown --output skill-report.md
python <skill-manager-root>/cli.py export --format json
```

也支持 CSV 和只读 HTML：

```bash
python <skill-manager-root>/cli.py export --format csv --output skill-report.csv
python <skill-manager-root>/cli.py export --format html --output skill-report.html
```

### 11. 备份与恢复

整合、恢复等覆盖性操作会把当前版本备份到 `~/.skill-manager/backups/`。

```bash
python <skill-manager-root>/cli.py backups
python <skill-manager-root>/cli.py restore --backup-id <backup-id>
```

如果当前没有同名 skill，需要显式指定恢复路径：

```bash
python <skill-manager-root>/cli.py restore --backup-id <backup-id> --target-path "C:/Users/me/.agents/skills/name"
```

### 12. 使用统计与隐私

使用统计是本地可选功能。它会读取 Grok、Codex、Claude 的本机会话日志，提取 skill 名称、Agent、事件时间、事件类型、会话 id、来源文件和 `SKILL.md` 路径片段，写入 `~/.skill-manager/usage-events.jsonl`。不会上传。

```bash
python <skill-manager-root>/cli.py usage-collect
python <skill-manager-root>/cli.py usage-stats --refresh
python <skill-manager-root>/cli.py usage-hooks-install
```

Web 面板默认只监听 `127.0.0.1`，并对 `/api/*` 请求启用本地会话 token。不要把面板直接暴露到公网。

### 13. 依赖、冲突、健康评分

扫描结果会包含 `dependencies`、`triggers`、`conflicts`、`health` 字段。查看缺失依赖：

```bash
python <skill-manager-root>/cli.py deps
python <skill-manager-root>/cli.py deps --name <skill-name>
```

安装缺失 Python 依赖必须显式确认：

```bash
python <skill-manager-root>/cli.py install-deps --name <skill-name> --yes
```

### 14. 导入导出、fork、模板、模糊搜索

```bash
python <skill-manager-root>/cli.py export-pkg --names "a,b" --output skills.skillpkg
python <skill-manager-root>/cli.py import-pkg --package skills.skillpkg --scope agents
python <skill-manager-root>/cli.py search "excel"
python <skill-manager-root>/cli.py fork --source xlsx --name xlsx-custom --scope agents
python <skill-manager-root>/cli.py templates
python <skill-manager-root>/cli.py from-template --template code-review --name my-code-review
```

### 15. 操作日志与自定义远程源

```bash
python <skill-manager-root>/cli.py audit --limit 50
python <skill-manager-root>/cli.py set-source --name my-skill --url "https://github.com/user/repo.git" --type github
```

### 16. 多机快照与智能清理

```bash
python <skill-manager-root>/cli.py snapshot --output office-pc.json
python <skill-manager-root>/cli.py diff-snapshot --snapshot office-pc.json
python <skill-manager-root>/cli.py cleanup-plan --refresh
python <skill-manager-root>/cli.py auto-cleanup --yes
```

`auto-cleanup` 会把候选项移入回收站，不会永久删除；默认不带 `--yes` 只输出计划。

## 交互要求

1. 删除前必须二次确认，说明将被删除的路径。
2. 安装前说明会写入哪个 scope。
3. 操作完成后重新 `scan`，把结果摘要告诉用户。
4. 不要删除用户未点名的 skills。
5. 如果用户没有装 Cursor/Codex，不要假设这些 agent 已配置；只报告扫描到的实际情况。

## 依赖

```bash
pip install -r <skill-manager-root>/requirements.txt
```

至少需要：`fastapi`、`uvicorn`、`pyyaml`。
