"""Project constants."""

GITHUB_USER = "funnaz"
GITHUB_REPO = "skill-manager"
GITHUB_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}"
GITHUB_CLONE_URL = f"{GITHUB_URL}.git"
GITHUB_INSTALL_CMD = (
    f'python cli.py install --git "{GITHUB_CLONE_URL}" --scope grok'
)