#!/usr/bin/env python3.14
import sys
if sys.version_info < (3, 14):
    sys.exit("Python 3.14+ required")
# files = off ✓
"""
CatCode 0.1 — VS Code–shaped IDE · Cursor vibe coding · CatSeek R1 Agent
=======================================================================
PR files = off · import python 3.14 · files = off

Layout mirrors VS Code (activity bar, sidebar, editor, panel, status).
Agent pane behaves like GitHub Copilot Chat Agent, powered by CatSeek R1.
Vibe coding follows Cursor: Agent / Ask / Plan · apply code into the editor.
"""
import ast
import importlib.util
import keyword
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from tkinter import font as tkfont, messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────
# IDENTITY · THEME (blue hue · blue text · black buttons)
# ──────────────────────────────────────────────────────────────
APP_NAME = "CatCode"
APP_VERSION = "0.1"
WINDOW_TITLE = "CatCode 0.1"
FILES_MODE = "off"  # PR files = off

BG = "#0a0e1a"
ACTIVITY_BG = "#070b14"
SIDEBAR_BG = "#0b101f"
EDITOR_BG = "#0d1220"
PANEL_BG = "#0a0f1c"
TAB_BG = "#0b101f"
TAB_ACTIVE = "#0d1220"
INPUT_BG = "#080c16"
STATUS_BG = "#0d47a1"

FG = "#3b82f6"          # blue text
FG_BRIGHT = "#60a5fa"
FG_DIM = "#2563eb"
FG_FAINT = "#1e3a8a"
ACCENT = "#3b82f6"
SEL_BG = "#1a3a6b"
CURLINE = "#101830"
BTN_BG = "#000000"      # black buttons
BTN_FG = "#3b82f6"      # blue text on black
BTN_HOVER = "#0d1b3d"
OK_GREEN = "#4dd0a1"
ERR_RED = "#ff6b7a"
WARN_YEL = "#e5c07b"

SYNTAX = {
    "kw": "#6f9fff",
    "builtin": "#4dd0e1",
    "string": "#8ab4ff",
    "comment": "#33507d",
    "number": "#40c4ff",
    "deco": "#448aff",
    "defname": "#b8d4ff",
}

IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"
MOD_LABEL = "⌘" if IS_MAC else "Ctrl+"

# Candidate paths for CatSeek R1 (cloned as Copilot Agent backend)
_CATSEEK_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "catseekr1.py"),
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "catseekr11.0--main",
        "catseekr1.py",
    ),
    "/Volumes/1TB/:STUFF~ /:Coding~/catseekr11.0--main/catseekr1.py",
]


def ui_font(size: int = 12, weight: str = "normal") -> tkfont.Font:
    family = "SF Pro Text" if IS_MAC else "Segoe UI"
    try:
        return tkfont.Font(family=family, size=size, weight=weight)
    except tk.TclError:
        return tkfont.Font(family="Helvetica", size=size, weight=weight)


def mono_font(size: int = 13) -> tkfont.Font:
    family = "Menlo" if IS_MAC else "Consolas"
    try:
        return tkfont.Font(family=family, size=size)
    except tk.TclError:
        return tkfont.Font(family="Courier", size=size)


# ──────────────────────────────────────────────────────────────
# CatSeek R1 loader (in-memory engine · files = off)
# ──────────────────────────────────────────────────────────────
def _find_catseek() -> Optional[str]:
    for path in _CATSEEK_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


def load_catseek_engine():
    """Import CatSeek R1 and return (module, CatR11Engine instance)."""
    path = _find_catseek()
    if not path:
        raise FileNotFoundError(
            "CatSeek R1 not found. Place catseekr1.py beside this IDE or at "
            "catseekr11.0--main/catseekr1.py"
        )
    spec = importlib.util.spec_from_file_location("catseekr1_agent", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load CatSeek from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["catseekr1_agent"] = mod
    spec.loader.exec_module(mod)

    # PR files = off — keep engine in-memory, no weight/model packing
    cfg = getattr(mod, "CONFIG", None)
    if isinstance(cfg, dict):
        cfg["files"] = "off"
        cfg["bitnet_no_weight_files"] = True
        cfg["api_enabled"] = False
        cfg["catcode_no_api"] = True
        cfg["vibe_code_heuristics"] = True

    engine = mod.CatR11Engine()
    return mod, engine, path


FENCE_RE = re.compile(r"```(?:([\w.+-]*)\n)?(.*?)```", re.S)


def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
    """Return list of (lang, code) from markdown fences."""
    blocks = []
    for m in FENCE_RE.finditer(text or ""):
        lang = (m.group(1) or "python").strip().lower()
        code = (m.group(2) or "").strip("\n")
        if code.strip():
            blocks.append((lang, code))
    return blocks


# ──────────────────────────────────────────────────────────────
# Editor (VS Code–style with line numbers + light syntax)
# ──────────────────────────────────────────────────────────────
class Editor(tk.Frame):
    def __init__(self, master, app, title: str = "untitled.py"):
        super().__init__(master, bg=EDITOR_BG)
        self.app = app
        self.title = title
        self.dirty = False
        self.mono = mono_font(13)

        self.linenos = tk.Text(
            self, width=5, padx=8, takefocus=0, bd=0, bg=EDITOR_BG,
            fg=FG_FAINT, font=self.mono, state="disabled",
            highlightthickness=0, cursor="arrow",
        )
        self.linenos.pack(side="left", fill="y")

        self.text = tk.Text(
            self, wrap="none", undo=True, bd=0, padx=10, pady=8,
            bg=EDITOR_BG, fg=FG, insertbackground=FG_BRIGHT,
            insertwidth=2, selectbackground=SEL_BG,
            selectforeground=FG_BRIGHT, font=self.mono,
            highlightthickness=0, tabs=(self.mono.measure("    "),),
        )
        self.text.pack(side="left", fill="both", expand=True)

        ysb = tk.Scrollbar(
            self, orient="vertical", command=self._yscroll,
            troughcolor=EDITOR_BG, bg=SIDEBAR_BG, bd=0,
            activebackground=FG_DIM, highlightthickness=0,
            relief="flat", width=10,
        )
        ysb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=lambda a, b: (ysb.set(a, b), self._sync()))

        self.text.tag_configure("curline", background=CURLINE)
        for tag, color in SYNTAX.items():
            self.text.tag_configure(tag, foreground=color)
        self.text.tag_raise("sel")

        self.text.bind("<KeyRelease>", self._on_change)
        self.text.bind("<ButtonRelease-1>", lambda e: self._cursor_moved())
        self.text.bind("<Return>", self._auto_indent)
        self.text.bind("<Tab>", self._soft_tab)
        self.text.bind("<<Modified>>", self._on_modified)
        self._sync()

    def _yscroll(self, *args):
        self.text.yview(*args)
        self._sync()

    def _sync(self):
        lines = int(self.text.index("end-1c").split(".")[0])
        self.linenos.configure(state="normal")
        self.linenos.delete("1.0", "end")
        self.linenos.insert("1.0", "\n".join(str(i) for i in range(1, lines + 1)))
        self.linenos.configure(state="disabled")
        self.linenos.yview_moveto(self.text.yview()[0])

    def _auto_indent(self, _e):
        line = self.text.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group(0)
        if line.rstrip().endswith(":"):
            indent += "    "
        self.text.insert("insert", "\n" + indent)
        self.after_idle(self._on_change)
        return "break"

    def _soft_tab(self, _e):
        self.text.insert("insert", "    ")
        return "break"

    def _on_modified(self, _e=None):
        if self.text.edit_modified():
            self.dirty = True
            self.text.edit_modified(False)
            self.app._refresh_tab_labels()

    def _on_change(self, _e=None):
        self._highlight()
        self._cursor_moved()
        self._sync()

    def _cursor_moved(self):
        self.text.tag_remove("curline", "1.0", "end")
        self.text.tag_add("curline", "insert linestart", "insert lineend+1c")
        self.app.update_cursor_status()

    def get(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_content(self, content: str, *, mark_clean: bool = True):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        if mark_clean:
            self.dirty = False
            self.text.edit_modified(False)
        self._on_change()

    def apply_code(self, code: str, *, replace: bool = True):
        if replace:
            self.set_content(code, mark_clean=False)
            self.dirty = True
        else:
            self.text.insert("insert", "\n" + code + "\n")
            self.dirty = True
        self.app._refresh_tab_labels()
        self._on_change()

    def _highlight(self):
        content = self.get()
        for tag in SYNTAX:
            self.text.tag_remove(tag, "1.0", "end")
        if not self.title.endswith((".py", ".pyw")):
            return
        # comments
        for m in re.finditer(r"#.*?$", content, re.M):
            self._tag_span("comment", m.start(), m.end())
        # strings
        for m in re.finditer(r"('''.*?'''|\"\"\".*?\"\"\"|'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")",
                             content, re.S):
            self._tag_span("string", m.start(), m.end())
        # numbers
        for m in re.finditer(r"\b\d+(?:\.\d+)?\b", content):
            self._tag_span("number", m.start(), m.end())
        # keywords / defs
        for m in re.finditer(r"\b([A-Za-z_]\w*)\b", content):
            word = m.group(1)
            if word in keyword.kwlist:
                self._tag_span("kw", m.start(), m.end())
            elif word in dir(__builtins__):
                self._tag_span("builtin", m.start(), m.end())
        for m in re.finditer(r"\b(def|class)\s+([A-Za-z_]\w*)", content):
            self._tag_span("defname", m.start(2), m.end(2))
        for m in re.finditer(r"@\w+", content):
            self._tag_span("deco", m.start(), m.end())

    def _tag_span(self, tag: str, start: int, end: int):
        self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")


# ──────────────────────────────────────────────────────────────
# CatCode IDE
# ──────────────────────────────────────────────────────────────
class CatCode(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("1500x920")
        self.minsize(1000, 620)
        self.configure(bg=BG)

        self.ui_queue: queue.Queue = queue.Queue()
        self.mode = tk.StringVar(value="Agent")  # Agent | Ask | Plan (Cursor vibe)
        self.engine = None
        self.catseek = None
        self.catseek_path = ""
        self.engine_ready = False
        self.busy = False
        self.tabs: Dict[str, Dict[str, Any]] = {}
        self.active_key: Optional[str] = None
        self._buffers: Dict[str, str] = {}  # in-memory workspace · files = off
        self._untitled_n = 1
        self.last_agent_code = ""

        self._style_ttk()
        self._build_menu()
        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self._quit_app)

        self.after(60, self._pump)
        self._open_welcome()
        threading.Thread(target=self._boot_engine, daemon=True).start()

    # ── theme helpers ─────────────────────────────────────────
    def _style_ttk(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(
            "Cat.Treeview",
            background=SIDEBAR_BG, fieldbackground=SIDEBAR_BG, foreground=FG,
            bordercolor=SIDEBAR_BG, borderwidth=0, font=ui_font(11), rowheight=24,
        )
        st.map(
            "Cat.Treeview",
            background=[("selected", SEL_BG)],
            foreground=[("selected", FG_BRIGHT)],
        )

    def _btn(self, parent, label, cmd, size=11, pad=(10, 4)):
        b = tk.Button(
            parent, text=label, command=cmd, bg=BTN_BG, fg=BTN_FG,
            activebackground=BTN_HOVER, activeforeground=FG_BRIGHT,
            bd=0, padx=pad[0], pady=pad[1], font=ui_font(size, "bold"),
            cursor="hand2", highlightthickness=0, relief="flat",
        )
        b.bind("<Enter>", lambda e: b.configure(bg=BTN_HOVER))
        b.bind("<Leave>", lambda e: b.configure(bg=BTN_BG))
        return b

    # ── menu ──────────────────────────────────────────────────
    def _build_menu(self):
        m = tk.Menu(self)
        filem = tk.Menu(m, tearoff=0)
        filem.add_command(label="New File", accelerator=f"{MOD_LABEL}N", command=self.new_file)
        filem.add_command(label="Close Editor", command=self.close_active)
        filem.add_separator()
        filem.add_command(label="Quit", accelerator=f"{MOD_LABEL}Q", command=self._quit_app)
        m.add_cascade(label="File", menu=filem)

        viewm = tk.Menu(m, tearoff=0)
        viewm.add_command(label="Command Palette…", accelerator=f"{MOD_LABEL}⇧P",
                          command=self.command_palette)
        viewm.add_command(label="Toggle Sidebar", accelerator=f"{MOD_LABEL}B",
                          command=self.toggle_sidebar)
        viewm.add_command(label="Toggle Panel", accelerator=f"{MOD_LABEL}J",
                          command=self.toggle_panel)
        viewm.add_command(label="Toggle Agent", accelerator=f"{MOD_LABEL}I",
                          command=self.toggle_agent)
        m.add_cascade(label="View", menu=viewm)

        runm = tk.Menu(m, tearoff=0)
        runm.add_command(label="Run Active Buffer", accelerator=f"{MOD_LABEL}R",
                         command=self.run_active)
        runm.add_command(label="Apply Last Agent Code", command=self.apply_last_code)
        m.add_cascade(label="Run", menu=runm)

        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="About CatCode", command=self.show_about)
        m.add_cascade(label="Help", menu=helpm)
        self.configure(menu=m)

    # ── layout (VS Code chrome) ───────────────────────────────
    def _build_ui(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # activity bar
        act = tk.Frame(body, bg=ACTIVITY_BG, width=48)
        act.pack(side="left", fill="y")
        act.pack_propagate(False)
        self._act_buttons = {}
        for icon, key, _tip in (
            ("📁", "explorer", "Explorer"),
            ("🔍", "search", "Search"),
            ("✦", "agent", "Copilot Agent"),
            ("▷", "run", "Run / Output"),
        ):
            b = tk.Button(
                act, text=icon, bd=0, bg=ACTIVITY_BG, fg=FG_DIM,
                activebackground=ACTIVITY_BG, activeforeground=ACCENT,
                font=("Helvetica", 16), cursor="hand2", highlightthickness=0,
                command=lambda k=key: self._activity(k),
            )
            b.pack(pady=(14 if not self._act_buttons else 6, 0))
            self._act_buttons[key] = b
        tk.Label(act, text="🐱", bg=ACTIVITY_BG, fg=FG_DIM,
                 font=("Helvetica", 16)).pack(side="bottom", pady=12)

        self.hpane = tk.PanedWindow(
            body, orient="horizontal", bg=BG, sashwidth=4, bd=0,
            sashrelief="flat", opaqueresize=True,
        )
        self.hpane.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        self._build_center()
        self._build_agent_pane()

        self.hpane.add(self.sidebar, minsize=170, width=240)
        self.hpane.add(self.center, minsize=420, stretch="always")
        self.hpane.add(self.agent_pane, minsize=320, width=420)

        self._build_status()
        self._activity("explorer")

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.hpane, bg=SIDEBAR_BG)

        self.explorer_view = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        head = tk.Frame(self.explorer_view, bg=SIDEBAR_BG)
        head.pack(fill="x")
        tk.Label(
            head, text="EXPLORER", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(10, "bold"), anchor="w", padx=12, pady=8,
        ).pack(side="left")
        self._btn(head, "+", self.new_file, size=10, pad=(6, 2)).pack(side="right", padx=6)

        tk.Label(
            self.explorer_view,
            text="OPEN EDITORS  ·  files = off",
            bg=SIDEBAR_BG, fg=FG_FAINT, font=ui_font(9),
            anchor="w", padx=12,
        ).pack(fill="x")

        self.buffer_list = tk.Listbox(
            self.explorer_view, bg=SIDEBAR_BG, fg=FG, bd=0,
            selectbackground=SEL_BG, selectforeground=FG_BRIGHT,
            font=ui_font(11), highlightthickness=0, activestyle="none",
        )
        self.buffer_list.pack(fill="both", expand=True, padx=6, pady=8)
        self.buffer_list.bind("<<ListboxSelect>>", self._buffer_select)

        # search view
        self.search_view = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        tk.Label(
            self.search_view, text="SEARCH", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(10, "bold"), anchor="w", padx=12, pady=8,
        ).pack(fill="x")
        self.search_entry = tk.Entry(
            self.search_view, bg=INPUT_BG, fg=FG_BRIGHT, bd=0,
            insertbackground=FG_BRIGHT, font=ui_font(12),
            highlightthickness=1, highlightbackground=FG_FAINT, highlightcolor=ACCENT,
        )
        self.search_entry.pack(fill="x", padx=10, ipady=5)
        self.search_entry.bind("<Return>", lambda e: self.run_search())
        self.search_results = tk.Listbox(
            self.search_view, bg=SIDEBAR_BG, fg=FG, bd=0,
            selectbackground=SEL_BG, selectforeground=FG_BRIGHT,
            font=ui_font(10), highlightthickness=0, activestyle="none",
        )
        self.search_results.pack(fill="both", expand=True, padx=6, pady=8)
        self.search_results.bind("<Double-1>", self._search_open)
        self._search_hits: List[Tuple[str, int, str]] = []

    def _build_center(self):
        self.center = tk.Frame(self.hpane, bg=BG)

        # tab strip
        self.tab_bar = tk.Frame(self.center, bg=TAB_BG, height=36)
        self.tab_bar.pack(fill="x")
        self.tab_bar.pack_propagate(False)
        self.tab_row = tk.Frame(self.tab_bar, bg=TAB_BG)
        self.tab_row.pack(side="left", fill="y")

        # editor host + bottom panel
        self.vpane = tk.PanedWindow(
            self.center, orient="vertical", bg=BG, sashwidth=4, bd=0,
            sashrelief="flat",
        )
        self.vpane.pack(fill="both", expand=True)

        self.editor_host = tk.Frame(self.vpane, bg=EDITOR_BG)
        self.empty_editor = tk.Label(
            self.editor_host,
            text=f"{APP_NAME} {APP_VERSION}\nOpen a buffer or ask the Agent to vibe code",
            bg=EDITOR_BG, fg=FG_DIM, font=ui_font(14), justify="center",
        )
        self.empty_editor.place(relx=0.5, rely=0.45, anchor="center")

        self.panel = tk.Frame(self.vpane, bg=PANEL_BG)
        phead = tk.Frame(self.panel, bg=PANEL_BG)
        phead.pack(fill="x")
        self._panel_tabs = {}
        for name in ("TERMINAL", "OUTPUT", "PROBLEMS"):
            b = tk.Button(
                phead, text=name, bd=0, bg=PANEL_BG, fg=FG_DIM,
                activebackground=PANEL_BG, activeforeground=FG_BRIGHT,
                font=ui_font(10, "bold"), cursor="hand2", padx=12, pady=6,
                command=lambda n=name: self.show_panel_tab(n),
            )
            b.pack(side="left")
            self._panel_tabs[name] = b

        self.panel_body = tk.Frame(self.panel, bg=PANEL_BG)
        self.panel_body.pack(fill="both", expand=True)

        self.terminal = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=10, pady=8,
        )
        self.output = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=10, pady=8,
        )
        self.problems = scrolledtext.ScrolledText(
            self.panel_body, wrap="word", bg=INPUT_BG, fg=WARN_YEL,
            insertbackground=FG_BRIGHT, font=mono_font(12),
            relief="flat", bd=0, padx=10, pady=8,
        )
        self._term_input = tk.Entry(
            self.panel, bg=BTN_BG, fg=FG, insertbackground=FG,
            relief="flat", font=mono_font(12),
        )
        self._term_input.pack(fill="x", side="bottom", padx=4, pady=4)
        self._term_input.bind("<Return>", self._term_run)
        self._term_input.insert(0, "")

        self.vpane.add(self.editor_host, minsize=220, stretch="always")
        self.vpane.add(self.panel, minsize=120, height=180)
        self.show_panel_tab("OUTPUT")
        self._panel_visible = True

    def _build_agent_pane(self):
        """GitHub Copilot–style Agent chat · CatSeek R1 backend."""
        self.agent_pane = tk.Frame(self.hpane, bg=SIDEBAR_BG)
        self._agent_visible = True

        head = tk.Frame(self.agent_pane, bg=SIDEBAR_BG)
        head.pack(fill="x")
        tk.Label(
            head, text="✦ AGENT", bg=SIDEBAR_BG, fg=FG_BRIGHT,
            font=ui_font(11, "bold"), anchor="w", padx=12, pady=8,
        ).pack(side="left")
        tk.Label(
            head, text="CatSeek R1", bg=SIDEBAR_BG, fg=FG_DIM,
            font=ui_font(9), padx=8,
        ).pack(side="right")

        # Cursor vibe modes: Agent / Ask / Plan
        modes = tk.Frame(self.agent_pane, bg=SIDEBAR_BG)
        modes.pack(fill="x", padx=10, pady=(0, 6))
        self._mode_btns = {}
        for name in ("Agent", "Ask", "Plan"):
            b = tk.Button(
                modes, text=name, bd=0, bg=BTN_BG, fg=BTN_FG,
                activebackground=BTN_HOVER, activeforeground=FG_BRIGHT,
                font=ui_font(10, "bold"), cursor="hand2", padx=12, pady=5,
                command=lambda n=name: self.set_mode(n),
            )
            b.pack(side="left", padx=(0, 6))
            self._mode_btns[name] = b
        self._refresh_mode_btns()

        self.agent_chat = scrolledtext.ScrolledText(
            self.agent_pane, wrap="word", bg=EDITOR_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=ui_font(11),
            relief="flat", bd=0, padx=12, pady=10, state="disabled",
        )
        self.agent_chat.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.agent_chat.tag_configure("user", foreground=FG_BRIGHT)
        self.agent_chat.tag_configure("agent", foreground=FG)
        self.agent_chat.tag_configure("sys", foreground=FG_DIM)
        self.agent_chat.tag_configure("think", foreground=FG_FAINT)
        self.agent_chat.tag_configure("ok", foreground=OK_GREEN)

        tools = tk.Frame(self.agent_pane, bg=SIDEBAR_BG)
        tools.pack(fill="x", padx=8, pady=(0, 4))
        self._btn(tools, "Apply Code", self.apply_last_code, size=10).pack(side="left")
        self._btn(tools, "Clear", self.clear_agent, size=10).pack(side="left", padx=6)
        self.engine_chip = tk.Label(
            tools, text="engine…", bg=SIDEBAR_BG, fg=FG_DIM, font=ui_font(9),
        )
        self.engine_chip.pack(side="right")

        composer = tk.Frame(self.agent_pane, bg=SIDEBAR_BG)
        composer.pack(fill="x", padx=8, pady=(0, 10))
        self.ai_input = tk.Text(
            composer, height=3, wrap="word", bg=INPUT_BG, fg=FG,
            insertbackground=FG_BRIGHT, font=ui_font(11),
            relief="flat", bd=0, padx=10, pady=8,
            highlightthickness=1, highlightbackground=FG_FAINT, highlightcolor=ACCENT,
        )
        self.ai_input.pack(fill="x", side="left", expand=True)
        self.ai_input.bind("<Return>", self._agent_enter)
        self.ai_input.bind(f"<{MOD}-Return>", lambda e: None)  # allow newline? keep submit on Return

        send = self._btn(composer, "↑", self.send_agent, size=14, pad=(12, 10))
        send.pack(side="right", padx=(6, 0))

        self._agent_log(
            "sys",
            f"{WINDOW_TITLE} · Copilot-style Agent = CatSeek R1\n"
            f"Cursor vibe: Agent / Ask / Plan · files = {FILES_MODE}\n"
            "Describe what you want — I'll vibe code into the editor.",
        )

    def _build_status(self):
        bar = tk.Frame(self, bg=STATUS_BG, height=24)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status_left = tk.Label(
            bar, text=f"{APP_NAME} {APP_VERSION}  ·  files={FILES_MODE}",
            bg=STATUS_BG, fg="#dbeafe", font=ui_font(9), anchor="w", padx=10,
        )
        self.status_left.pack(side="left")
        self.status_right = tk.Label(
            bar, text="Ln 1, Col 1  ·  Python  ·  CatSeek R1",
            bg=STATUS_BG, fg="#dbeafe", font=ui_font(9), anchor="e", padx=10,
        )
        self.status_right.pack(side="right")

    # ── activity / panels ─────────────────────────────────────
    def _activity(self, key: str):
        for k, b in self._act_buttons.items():
            b.configure(fg=ACCENT if k == key else FG_DIM)
        if key == "agent":
            if not self._agent_visible:
                self.toggle_agent()
            self.ai_input.focus_set()
            return
        if key == "run":
            self.show_panel_tab("OUTPUT")
            return
        self.explorer_view.pack_forget()
        self.search_view.pack_forget()
        if key == "explorer":
            self.explorer_view.pack(fill="both", expand=True)
        elif key == "search":
            self.search_view.pack(fill="both", expand=True)
            self.search_entry.focus_set()

    def show_panel_tab(self, name: str):
        for n, b in self._panel_tabs.items():
            b.configure(fg=FG_BRIGHT if n == name else FG_DIM)
        self.terminal.pack_forget()
        self.output.pack_forget()
        self.problems.pack_forget()
        {"TERMINAL": self.terminal, "OUTPUT": self.output, "PROBLEMS": self.problems}[name].pack(
            fill="both", expand=True,
        )

    def toggle_sidebar(self):
        try:
            self.hpane.forget(self.sidebar)
            self._sidebar_hidden = True
        except tk.TclError:
            self.hpane.add(self.sidebar, minsize=170, width=240, before=self.center)
            self._sidebar_hidden = False

    def toggle_panel(self):
        if self._panel_visible:
            try:
                self.vpane.forget(self.panel)
            except tk.TclError:
                pass
            self._panel_visible = False
        else:
            self.vpane.add(self.panel, minsize=120, height=180)
            self._panel_visible = True

    def toggle_agent(self):
        if self._agent_visible:
            try:
                self.hpane.forget(self.agent_pane)
            except tk.TclError:
                pass
            self._agent_visible = False
        else:
            self.hpane.add(self.agent_pane, minsize=320, width=420)
            self._agent_visible = True

    def set_mode(self, name: str):
        self.mode.set(name)
        self._refresh_mode_btns()
        self.status_left.config(text=f"{APP_NAME} {APP_VERSION}  ·  {name}  ·  files={FILES_MODE}")

    def _refresh_mode_btns(self):
        cur = self.mode.get()
        for name, b in self._mode_btns.items():
            on = name == cur
            b.configure(fg=FG_BRIGHT if on else BTN_FG, bg="#111111" if on else BTN_BG)

    # ── keys ──────────────────────────────────────────────────
    def _bind_keys(self):
        self.bind(f"<{MOD}-n>", lambda e: self.new_file())
        self.bind(f"<{MOD}-q>", lambda e: self._quit_app())
        self.bind(f"<{MOD}-b>", lambda e: self.toggle_sidebar())
        self.bind(f"<{MOD}-j>", lambda e: self.toggle_panel())
        self.bind(f"<{MOD}-i>", lambda e: self.toggle_agent())
        self.bind(f"<{MOD}-r>", lambda e: self.run_active())
        self.bind(f"<{MOD}-Shift-p>", lambda e: self.command_palette())
        self.bind(f"<{MOD}-Shift-P>", lambda e: self.command_palette())

    # ── buffers / tabs (in-memory · files = off) ─────────────
    def _open_welcome(self):
        key = "welcome.md"
        content = (
            f"# {WINDOW_TITLE}\n\n"
            "VS Code chrome · Cursor vibe coding · **CatSeek R1** Agent\n\n"
            f"- Engine: CatSeek R1 (Copilot Agent role)\n"
            f"- Files: `{FILES_MODE}` (in-memory buffers)\n"
            f"- Theme: blue hue · blue text · black buttons\n\n"
            "## Try\n"
            "1. Open the Agent pane (✦)\n"
            "2. Mode: **Agent** for vibe coding\n"
            "3. Ask: `write a fibonacci function in python`\n"
            "4. Click **Apply Code** into the editor\n"
            f"5. `{MOD_LABEL}R` to run\n"
        )
        self._open_buffer(key, content, activate=True)

    def new_file(self):
        name = f"untitled-{self._untitled_n}.py"
        self._untitled_n += 1
        self._open_buffer(name, "def main():\n    print('hello from CatCode')\n\nif __name__ == '__main__':\n    main()\n")

    def _open_buffer(self, key: str, content: str = "", *, activate: bool = True):
        if key in self.tabs:
            if activate:
                self._activate_tab(key)
            return
        ed = Editor(self.editor_host, self, title=key)
        ed.set_content(content)
        tab = tk.Frame(self.tab_row, bg=TAB_BG)
        lbl = tk.Label(tab, text=key, bg=TAB_BG, fg=FG_DIM, font=ui_font(10), padx=10, pady=6)
        lbl.pack(side="left")
        close = tk.Button(
            tab, text="×", bd=0, bg=TAB_BG, fg=FG_DIM, font=ui_font(10),
            command=lambda k=key: self.close_tab(k), cursor="hand2",
        )
        close.pack(side="left", padx=(0, 6))
        lbl.bind("<Button-1>", lambda e, k=key: self._activate_tab(k))
        tab.pack(side="left", fill="y")
        self.tabs[key] = {"editor": ed, "tab": tab, "label": lbl}
        self._buffers[key] = content
        self._refresh_buffer_list()
        if activate:
            self._activate_tab(key)

    def _activate_tab(self, key: str):
        if key not in self.tabs:
            return
        self.empty_editor.place_forget()
        for k, meta in self.tabs.items():
            meta["editor"].pack_forget()
            meta["tab"].configure(bg=TAB_BG)
            meta["label"].configure(bg=TAB_BG, fg=FG_DIM)
        meta = self.tabs[key]
        meta["editor"].pack(fill="both", expand=True)
        meta["tab"].configure(bg=TAB_ACTIVE)
        meta["label"].configure(bg=TAB_ACTIVE, fg=FG_BRIGHT)
        self.active_key = key
        self.update_cursor_status()
        self._sync_list_selection(key)

    def close_tab(self, key: str):
        if key not in self.tabs:
            return
        meta = self.tabs.pop(key)
        meta["editor"].destroy()
        meta["tab"].destroy()
        self._buffers.pop(key, None)
        self._refresh_buffer_list()
        if self.active_key == key:
            self.active_key = None
            if self.tabs:
                self._activate_tab(next(iter(self.tabs)))
            else:
                self.empty_editor.place(relx=0.5, rely=0.45, anchor="center")

    def close_active(self):
        if self.active_key:
            self.close_tab(self.active_key)

    def _refresh_tab_labels(self):
        for k, meta in self.tabs.items():
            dirty = " ●" if meta["editor"].dirty else ""
            meta["label"].configure(text=f"{k}{dirty}")

    def _refresh_buffer_list(self):
        self.buffer_list.delete(0, "end")
        for k in self.tabs:
            self.buffer_list.insert("end", k)

    def _sync_list_selection(self, key: str):
        keys = list(self.tabs.keys())
        if key in keys:
            idx = keys.index(key)
            self.buffer_list.selection_clear(0, "end")
            self.buffer_list.selection_set(idx)
            self.buffer_list.see(idx)

    def _buffer_select(self, _e=None):
        sel = self.buffer_list.curselection()
        if not sel:
            return
        key = self.buffer_list.get(sel[0])
        self._activate_tab(key)

    def active_editor(self) -> Optional[Editor]:
        if self.active_key and self.active_key in self.tabs:
            return self.tabs[self.active_key]["editor"]
        return None

    def update_cursor_status(self):
        ed = self.active_editor()
        if not ed:
            self.status_right.config(text="CatSeek R1  ·  ready")
            return
        idx = ed.text.index("insert")
        line, col = idx.split(".")
        lang = "Python" if ed.title.endswith(".py") else "Plain Text"
        engine = "CatSeek R1" if self.engine_ready else "booting…"
        self.status_right.config(text=f"Ln {line}, Col {int(col)+1}  ·  {lang}  ·  {engine}")

    # ── search (in-memory buffers) ────────────────────────────
    def run_search(self):
        q = self.search_entry.get().strip()
        self.search_results.delete(0, "end")
        self._search_hits = []
        if not q:
            return
        for key, meta in self.tabs.items():
            text = meta["editor"].get()
            for i, line in enumerate(text.splitlines(), 1):
                if q.lower() in line.lower():
                    self._search_hits.append((key, i, line.strip()[:80]))
                    self.search_results.insert("end", f"{key}:{i}  {line.strip()[:80]}")

    def _search_open(self, _e=None):
        sel = self.search_results.curselection()
        if not sel:
            return
        key, line, _ = self._search_hits[sel[0]]
        self._activate_tab(key)
        ed = self.active_editor()
        if ed:
            ed.text.mark_set("insert", f"{line}.0")
            ed.text.see(f"{line}.0")
            ed._cursor_moved()

    # ── agent (CatSeek R1 = Copilot Agent) ────────────────────
    def _boot_engine(self):
        try:
            mod, engine, path = load_catseek_engine()
            self.ui_queue.put(("engine_ok", mod, engine, path))
        except Exception as e:
            self.ui_queue.put(("engine_err", str(e)))

    def _pump(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                kind = item[0]
                if kind == "engine_ok":
                    _, mod, engine, path = item
                    self.catseek = mod
                    self.engine = engine
                    self.catseek_path = path
                    self.engine_ready = True
                    self.engine_chip.config(text="CatSeek R1 · files=off", fg=OK_GREEN)
                    self._agent_log("ok", f"Agent online · CatSeek R1\n{path}")
                    self.update_cursor_status()
                elif kind == "engine_err":
                    self.engine_chip.config(text="engine offline", fg=ERR_RED)
                    self._agent_log("sys", f"Could not load CatSeek R1:\n{item[1]}")
                elif kind == "agent_out":
                    _, prompt, reply, think = item
                    if think:
                        self._agent_log("think", f"thinking…\n{think[:1200]}")
                    self._agent_log("agent", reply)
                    blocks = extract_code_blocks(reply)
                    if blocks:
                        lang, code = blocks[0]
                        self.last_agent_code = code
                        if self.mode.get() == "Agent":
                            # Cursor vibe: auto-apply into editor for Agent mode
                            self._vibe_apply(lang, code)
                        else:
                            self._agent_log("sys", "Code ready — click Apply Code (Ask/Plan won't auto-write).")
                    self.busy = False
                    self.status_left.config(
                        text=f"{APP_NAME} {APP_VERSION}  ·  {self.mode.get()}  ·  files={FILES_MODE}"
                    )
                elif kind == "agent_err":
                    self._agent_log("sys", f"Agent error: {item[1]}")
                    self.busy = False
                elif kind == "run_out":
                    self.show_panel_tab("OUTPUT")
                    self.output.insert("end", item[1] + "\n")
                    self.output.see("end")
                elif kind == "run_err":
                    self.show_panel_tab("PROBLEMS")
                    self.problems.insert("end", item[1] + "\n")
                    self.problems.see("end")
        except queue.Empty:
            pass
        self.after(60, self._pump)

    def _agent_log(self, tag: str, text: str):
        self.agent_chat.configure(state="normal")
        prefix = {"user": "You", "agent": "Agent", "sys": "System", "think": "Think", "ok": "OK"}.get(tag, tag)
        self.agent_chat.insert("end", f"{prefix}\n", tag)
        self.agent_chat.insert("end", text.rstrip() + "\n\n", tag)
        self.agent_chat.see("end")
        self.agent_chat.configure(state="disabled")

    def _agent_enter(self, e):
        if e.state & 0x1:  # Shift+Return → newline
            return None
        self.send_agent()
        return "break"

    def send_agent(self):
        if self.busy:
            return
        raw = self.ai_input.get("1.0", "end-1c").strip()
        if not raw:
            return
        if not self.engine_ready or self.engine is None:
            self._agent_log("sys", "CatSeek R1 still booting — try again in a moment.")
            return
        self.ai_input.delete("1.0", "end")
        mode = self.mode.get()
        ed = self.active_editor()
        ctx = ""
        if ed and mode in {"Agent", "Ask", "Plan"}:
            buf = ed.get()
            if buf.strip():
                ctx = f"\n\n[Active buffer: {ed.title}]\n```python\n{buf[:4000]}\n```"
        prompt = self._compose_prompt(mode, raw, ctx)
        self._agent_log("user", raw)
        self.busy = True
        self.status_left.config(text=f"{APP_NAME}  ·  Agent thinking…")
        threading.Thread(target=self._agent_worker, args=(raw, prompt), daemon=True).start()

    def _compose_prompt(self, mode: str, user: str, ctx: str) -> str:
        """Cursor-style system framing for vibe coding."""
        if mode == "Ask":
            return (
                f"[CatCode Ask mode — explain only, minimal code unless asked]\n"
                f"{user}{ctx}"
            )
        if mode == "Plan":
            return (
                f"[CatCode Plan mode — outline steps for the change, then optional sketch]\n"
                f"{user}{ctx}"
            )
        # Agent = Copilot Agent vibe coding
        return (
            f"[CatCode Agent · CatSeek R1 · vibe code · files=off]\n"
            f"Write concrete code in fenced blocks. Prefer Python 3.14.\n"
            f"User request: {user}{ctx}"
        )

    def _agent_worker(self, display_prompt: str, prompt: str):
        try:
            # Prefer /catrcode for coding; otherwise plain generate
            engine = self.engine
            pl = display_prompt.lower()
            if any(w in pl for w in ("code", "write", "build", "make", "vibe", "function", "写", "做")):
                if not display_prompt.strip().startswith("/"):
                    call = f"/catrcode {display_prompt}"
                else:
                    call = prompt
            else:
                call = prompt
            reply = engine.generate(call)
            think = getattr(engine, "last_think", "") or ""
            self.ui_queue.put(("agent_out", display_prompt, reply, think))
        except Exception as e:
            self.ui_queue.put(("agent_err", str(e)))

    def _vibe_apply(self, lang: str, code: str):
        ext = {
            "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
            "typescript": ".ts", "html": ".html", "bash": ".sh", "rust": ".rs",
            "go": ".go", "c": ".c", "cpp": ".cpp",
        }.get(lang, ".py")
        ed = self.active_editor()
        if ed and (ed.title.endswith(ext) or ed.title.startswith("untitled") or ed.title.endswith(".py")):
            ed.apply_code(code, replace=True)
            self._agent_log("ok", f"Applied into `{ed.title}` (Agent vibe).")
            return
        name = f"agent-{self._untitled_n}{ext}"
        self._untitled_n += 1
        self._open_buffer(name, code)
        self._agent_log("ok", f"Opened `{name}` with agent code.")

    def apply_last_code(self):
        if not self.last_agent_code:
            self._agent_log("sys", "No agent code to apply yet.")
            return
        ed = self.active_editor()
        if not ed:
            self._open_buffer(f"untitled-{self._untitled_n}.py", self.last_agent_code)
            self._untitled_n += 1
            return
        ed.apply_code(self.last_agent_code, replace=True)
        self._agent_log("ok", f"Applied into `{ed.title}`.")

    def clear_agent(self):
        self.agent_chat.configure(state="normal")
        self.agent_chat.delete("1.0", "end")
        self.agent_chat.configure(state="disabled")
        if self.engine is not None:
            try:
                self.engine.clear_history()
            except Exception:
                pass
        self._agent_log("sys", "Agent chat cleared.")

    # ── run active buffer (in-memory via exec) ────────────────
    def run_active(self):
        ed = self.active_editor()
        if not ed:
            return
        src = ed.get()
        self.show_panel_tab("OUTPUT")
        self.output.insert("end", f"▶ run {ed.title}\n")
        self.output.see("end")

        def worker():
            import io
            import contextlib
            buf = io.StringIO()
            try:
                # syntax check first
                ast.parse(src)
                g: Dict[str, Any] = {"__name__": "__main__"}
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    exec(compile(src, ed.title, "exec"), g, g)
                out = buf.getvalue() or "(no output)"
                self.ui_queue.put(("run_out", out))
            except SyntaxError as e:
                self.ui_queue.put(("run_err", f"SyntaxError: {e}"))
            except Exception as e:
                self.ui_queue.put(("run_err", f"{type(e).__name__}: {e}"))

        if ed.title.endswith((".py", ".pyw")) or "def " in src:
            threading.Thread(target=worker, daemon=True).start()
        else:
            self.output.insert("end", "(not a Python buffer — paste into Agent or rename *.py)\n")

    def _term_run(self, _e=None):
        cmd = self._term_input.get().strip()
        if not cmd:
            return
        self._term_input.delete(0, "end")
        self.show_panel_tab("TERMINAL")
        self.terminal.insert("end", f"$ {cmd}\n")
        # Lightweight shell — still files=off for model; terminal may run cmds
        def worker():
            try:
                p = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                )
                out = (p.stdout or "") + (p.stderr or "")
                self.ui_queue.put(("run_out", out or f"(exit {p.returncode})"))
            except Exception as e:
                self.ui_queue.put(("run_err", str(e)))
        # show in terminal via output pump → also mirror
        def term_worker():
            try:
                p = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                )
                out = (p.stdout or "") + (p.stderr or "") or f"(exit {p.returncode})\n"

                def ui():
                    self.terminal.insert("end", out if out.endswith("\n") else out + "\n")
                    self.terminal.see("end")
                self.after(0, ui)
            except Exception as e:
                self.after(0, lambda: self.terminal.insert("end", f"{e}\n"))
        threading.Thread(target=term_worker, daemon=True).start()

    # ── command palette ───────────────────────────────────────
    def command_palette(self):
        win = tk.Toplevel(self)
        win.title("Command Palette")
        win.configure(bg=BG)
        win.geometry("520x320")
        win.transient(self)
        entry = tk.Entry(
            win, bg=INPUT_BG, fg=FG_BRIGHT, insertbackground=FG_BRIGHT,
            font=ui_font(13), relief="flat",
        )
        entry.pack(fill="x", padx=12, pady=12, ipady=6)
        entry.focus_set()
        cmds = [
            ("New File", self.new_file),
            ("Toggle Agent", self.toggle_agent),
            ("Toggle Sidebar", self.toggle_sidebar),
            ("Toggle Panel", self.toggle_panel),
            ("Run Active", self.run_active),
            ("Apply Agent Code", self.apply_last_code),
            ("Mode: Agent", lambda: self.set_mode("Agent")),
            ("Mode: Ask", lambda: self.set_mode("Ask")),
            ("Mode: Plan", lambda: self.set_mode("Plan")),
            ("About", self.show_about),
        ]
        lb = tk.Listbox(
            win, bg=SIDEBAR_BG, fg=FG, font=ui_font(12),
            selectbackground=SEL_BG, highlightthickness=0,
        )
        lb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for label, _ in cmds:
            lb.insert("end", label)
        lb.selection_set(0)

        def run(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            cmds[sel[0]][1]()
            win.destroy()

        def filter_cmds(_e=None):
            q = entry.get().lower()
            lb.delete(0, "end")
            self._palette_filtered = [(l, f) for l, f in cmds if q in l.lower()]
            for l, _ in self._palette_filtered:
                lb.insert("end", l)
            if self._palette_filtered:
                lb.selection_set(0)

        self._palette_filtered = cmds

        def run_filtered(_e=None):
            sel = lb.curselection()
            items = getattr(self, "_palette_filtered", cmds)
            if not sel or not items:
                return
            items[sel[0]][1]()
            win.destroy()

        entry.bind("<KeyRelease>", filter_cmds)
        entry.bind("<Return>", run_filtered)
        lb.bind("<Double-1>", run_filtered)
        lb.bind("<Return>", run_filtered)

    def show_about(self):
        messagebox.showinfo(
            WINDOW_TITLE,
            f"{WINDOW_TITLE}\n\n"
            "VS Code–shaped IDE\n"
            "Cursor vibe coding (Agent / Ask / Plan)\n"
            "GitHub Copilot–style Agent = CatSeek R1\n"
            f"files = {FILES_MODE}\n"
            f"Python {sys.version.split()[0]}\n"
            f"Engine: {self.catseek_path or '(loading…)'}",
        )

    def _quit_app(self):
        if messagebox.askokcancel("Quit", f"Exit {WINDOW_TITLE}?"):
            if self.engine is not None:
                try:
                    self.engine.clear_history()
                except Exception:
                    pass
            self.destroy()


def main():
    app = CatCode()
    app.mainloop()


if __name__ == "__main__":
    main()
