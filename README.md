# Skill Manager

一个可安装的 Agent Skill，用来管理本机 Skills：扫描、可视化、创建、安装、禁用、删除、导出报告。

GitHub: **https://github.com/funnaz/skill-manager**

支持：
- **Grok Build**（`~/.grok/skills/`、内置 skills、marketplace）
- **共享 Agents**（`~/.agents/skills/`）
- **Cursor**（`~/.cursor/skills/`）
- **OpenAI Codex**（`~/.codex/skills/`）

## 快速安装

### Windows

```powershell
git clone https://github.com/funnaz/skill-manager.git
cd skill-manager
pip install -r requirements.txt
python cli.py install --git "https://github.com/funnaz/skill-manager.git" --scope grok
```

或使用脚本：

```powershell
.\scripts\install.ps1 -Scope grok
```

### macOS / Linux

```bash
git clone https://github.com/funnaz/skill-manager.git
cd skill-manager
pip install -r requirements.txt
python cli.py install --git "https://github.com/funnaz/skill-manager.git" --scope grok
```

## 使用

### 扫描

```bash
python cli.py scan
```

### 启动面板

```bash
python cli.py serve --port 5520
```

浏览器打开：http://127.0.0.1:5520

### 创建 Skill

```bash
python cli.py create --name my-skill --description "做什么、何时触发" --scope grok
```

### 安装 Skill

本地目录：

```bash
python cli.py install --from-path "C:/path/to/skill" --scope grok
```

GitHub：

```bash
python cli.py install --git "https://github.com/funnaz/wechat-public-account-coach.git" --scope agents
```

### 禁用 / 启用（Grok）

```bash
python cli.py disable --name my-skill
python cli.py enable --name my-skill
```

### 删除 Skill

```bash
python cli.py delete --name my-skill
python cli.py delete --batch "old-skill,another-skill"
```

### 检测新版本

```bash
python cli.py check-updates
python cli.py check-updates --names "dbs,lark-doc"
```

### 升级 Skill（GitHub 源）

```bash
python cli.py upgrade --name dbs
```

### 导出报告

```bash
python cli.py export --format markdown --output skill-report.md
python cli.py export --format json
```

## 在 Agent 里使用

安装后，对 Grok 说：

- `/skill-manager`
- `帮我扫描一下电脑里的 skills`
- `安装这个 GitHub skill`
- `禁用 xxx skill`
- `删除没用的 xxx skill`
- `导出 skill 报告`
- `打开 skill 面板`

## 发布

```bash
git remote add origin https://github.com/funnaz/skill-manager.git
git push -u origin main
```

## 目录结构

```text
skill-manager/
  SKILL.md
  README.md
  constants.py
  cli.py
  server.py
  scanner.py
  manager.py
  config_io.py
  report.py
  scripts/install.ps1
  scripts/install.sh
  static/index.html
```

## License

MIT