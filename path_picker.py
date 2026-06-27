"""Native folder picker for local dashboard."""

from __future__ import annotations


def pick_folder(title: str = "选择 Skill 目录") -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.update()
    path = filedialog.askdirectory(title=title, mustexist=True)
    root.destroy()
    return path or None