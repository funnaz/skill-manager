---
name: skill-manager
description: |
  管理本机 Agent Skills：扫描、可视化、创建、安装、删除。
  触发方式：/skill-manager、/skill管家、「帮我管理 skill」「安装新 skill」「删除无用 skill」「打开 skill 面板」
  Manage local agent skills: scan, visualize, create, install, delete.
  Trigger: /skill-manager, "manage my skills", "install a skill", "delete unused skill", "open skill dashboard".
metadata:
  short-description: "Scan, install, and delete local agent skills"
---

# Skill Manager

帮助用户管理本机 Agent Skills。默认支持 **Grok Build**、**Cursor**、**OpenAI Codex**，以及共享目录 `~/.agents/skills/`。

## 何时使用

- 用户想查看电脑里装了哪些 skills、分别挂在哪些 agent 上
- 用户想新建一个 skill 模板
- 用户想从本地目录或 GitHub 安装 skill
- 用户想删除不再使用的 skill
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
```

如果用户通过 `~/.grok/skills/skill-manager/` 安装，则 `<skill-manager-root>` 即该目录。

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

### 5. 删除无用 Skill

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

如果 skill 在 `~/.agents/skills/`，删除时同步清理相关 junction 桥接，并更新 `~/.agents/.skill-lock.json`。

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