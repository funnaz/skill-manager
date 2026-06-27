# Skill Manager

一个可安装的 Agent Skill，用来管理本机 Skills：扫描、可视化、创建、安装、删除。

支持：
- **Grok Build**（`~/.grok/skills/`、内置 skills、marketplace）
- **共享 Agents**（`~/.agents/skills/`）
- **Cursor**（`~/.cursor/skills/`）
- **OpenAI Codex**（`~/.codex/skills/`）

## 安装为 Skill

### 方式一：安装到 Grok 用户目录

```bash
git clone https://github.com/<your-user>/skill-manager.git
cp -r skill-manager ~/.grok/skills/skill-manager
```

Windows PowerShell:

```powershell
git clone https://github.com/<your-user>/skill-manager.git
Copy-Item -Recurse skill-manager $env:USERPROFILE\.grok\skills\skill-manager
```

### 方式二：通过本工具自安装

```bash
python cli.py install --git "https://github.com/<your-user>/skill-manager.git" --scope grok
```

## 依赖

```bash
pip install -r requirements.txt
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
python cli.py install --git "https://github.com/user/repo.git" --subpath "skills/my-skill" --scope agents
```

### 删除 Skill

```bash
python cli.py delete --name my-skill
```

受保护类型（Grok 内置、marketplace、依赖包内置、skill-manager 自身）不会被删除。

## 在 Agent 里使用

安装后，对 Grok 说：

- `/skill-manager`
- `帮我扫描一下电脑里的 skills`
- `安装这个 GitHub skill`
- `删除没用的 xxx skill`
- `打开 skill 面板`

## 发布到 GitHub

```bash
git init
git add .
git commit -m "Initial release: skill manager"
git branch -M main
git remote add origin https://github.com/<your-user>/skill-manager.git
git push -u origin main
```

## 目录结构

```text
skill-manager/
  SKILL.md          # Agent 工作流说明
  README.md
  cli.py            # 命令行入口
  server.py         # Web API + 面板
  scanner.py        # 扫描与 agent 映射
  manager.py        # 创建 / 安装 / 删除
  static/index.html
  requirements.txt
```

## License

MIT