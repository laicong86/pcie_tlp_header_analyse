# -*- coding: utf-8 -*-
"""PCIe TLP Header 解析器 —— tkinter 界面。"""

from __future__ import annotations

import os
import re
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import List, Optional

from tlp.parser import Line, ParseResult, parse

APP_TITLE = "PCIe TLP Header 解析器"

MODE_NFM = "Non-Flit Mode"
MODE_FM = "Flit Mode"

COLOR_BG = "#F4F5F7"
COLOR_CARD = "#FFFFFF"
COLOR_BORDER = "#D8DBE0"
COLOR_TITLE = "#1A3D7C"
COLOR_SECTION = "#0F6B4F"
COLOR_WARN = "#B3261E"
COLOR_ERR_BG = "#FDECEA"
COLOR_GOOD = "#1B7F3B"
COLOR_TEXT = "#3C4043"
COLOR_HINT = "#80868B"

SAMPLE_NFM = ["60010001", "00000000", "00000010", "9488BC00"]
SAMPLE_FM = ["60010001", "00000000", "00000000", "00000000"]


class App(object):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._after_id: Optional[str] = None

        root.title(APP_TITLE)
        root.configure(bg=COLOR_BG)

        try:
            self.ui_scale = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
        except tk.TclError:
            self.ui_scale = 1.0

        self._init_fonts()
        self._init_style()
        self._build()
        self._load_sample()  # 启动时带一组示例数据
        self._fit_window()
        # 冻结为 exe 时首帧可能来不及绘制部分控件，强制同步刷新一次
        self.root.update_idletasks()
        self.root.update()

    # ------------------------------------------------------------ 初始化
    def _init_fonts(self) -> None:
        families = set(tkfont.families())
        ui = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else "Segoe UI"
        mono = "Consolas" if "Consolas" in families else "Courier New"
        self.f_ui = (ui, 10)
        self.f_ui_bold = (ui, 10, "bold")
        self.f_small = (ui, 9)
        self.f_mono = (mono, 10)
        self.f_entry = (mono, 13)

    def _init_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=self.f_ui)
        style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=self.f_ui)
        style.configure("Title.TLabel", background=COLOR_CARD, foreground=COLOR_TITLE, font=(self.f_ui[0], 12, "bold"))
        style.configure("Hint.TLabel", background=COLOR_CARD, foreground=COLOR_HINT, font=self.f_small)
        style.configure("TButton", font=self.f_ui, padding=(10, 4))
        style.configure("Accent.TButton", font=self.f_ui_bold, padding=(12, 5))
        style.configure("TCombobox", font=self.f_ui)
        style.configure("DW.TLabel", background=COLOR_CARD, foreground=COLOR_HINT, font=(self.f_ui[0], 9))

    # ------------------------------------------------------------ 布局
    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        # ---- 顶部卡片：模式 + 4 个 DW 输入 ----
        card = tk.Frame(outer, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="x")

        inner = tk.Frame(card, bg=COLOR_CARD, padx=18, pady=14)
        inner.pack(fill="x")

        # 单行：Model + 4 个 DW 输入 + 操作按钮
        row = tk.Frame(inner, bg=COLOR_CARD)
        row.pack(fill="x")

        m_cell = tk.Frame(row, bg=COLOR_CARD)
        m_cell.pack(side="left", padx=(0, 20))
        tk.Label(m_cell, text="Model", bg=COLOR_CARD, fg=COLOR_HINT,
                 font=(self.f_ui[0], 9)).pack(anchor="w")
        self.mode_var = tk.StringVar(value=MODE_NFM)
        self.mode_box = ttk.Combobox(m_cell, textvariable=self.mode_var, state="readonly",
                                     values=[MODE_NFM, MODE_FM], width=15, font=self.f_ui)
        self.mode_box.pack()
        self.mode_box.bind("<<ComboboxSelected>>", lambda e: self._on_change())

        self.dw_vars: List[tk.StringVar] = []
        self.dw_entries: List[tk.Entry] = []
        for i in range(4):
            cell = tk.Frame(row, bg=COLOR_CARD)
            cell.pack(side="left", padx=(0, 12))
            tk.Label(cell, text="DW{}".format(i), bg=COLOR_CARD, fg=COLOR_HINT,
                     font=(self.f_ui[0], 9)).pack(anchor="w")
            var = tk.StringVar()
            entry = tk.Entry(cell, textvariable=var, width=10, justify="center",
                             font=self.f_entry, relief="flat", bg="#F1F3F6",
                             fg="#1F2937", insertbackground="#1F2937",
                             highlightthickness=1, highlightbackground=COLOR_BORDER,
                             highlightcolor="#3B82F6")
            entry.pack(ipady=4)
            entry.bind("<KeyRelease>", self._on_key)
            entry.bind("<Return>", self._on_key)
            entry.bind("<<Paste>>", self._on_paste, add="+")
            self.dw_vars.append(var)
            self.dw_entries.append(entry)
        self.dw_entries[0].focus_set()

        btns = tk.Frame(row, bg=COLOR_CARD)
        btns.pack(side="right", anchor="s")
        ttk.Button(btns, text="清空", command=self._clear).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="示例", command=self._load_sample).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="解析", style="Accent.TButton", command=self._on_change).pack(side="right")

        foot = tk.Frame(inner, bg=COLOR_CARD)
        foot.pack(fill="x", pady=(8, 0))
        tk.Label(foot, text="每格 8 位十六进制（1 DW，高位在前）；不足 4 DW 可留空；也可把整行粘到 DW0。",
                 bg=COLOR_CARD, fg=COLOR_HINT, font=self.f_small).pack(side="left")
        self.status = tk.Label(foot, text="", bg=COLOR_CARD, fg=COLOR_HINT, font=self.f_small)
        self.status.pack(side="right")

        # ---- 输出区 ----
        out_card = tk.Frame(outer, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                            highlightthickness=1, bd=0)
        out_card.pack(fill="both", expand=True)

        head = tk.Frame(out_card, bg=COLOR_CARD, padx=18, pady=12)
        head.pack(fill="x")
        tk.Label(head, text="解析：", bg=COLOR_CARD, fg=COLOR_TITLE,
                 font=(self.f_ui[0], 11, "bold")).pack(side="left")

        body = tk.Frame(out_card, bg=COLOR_CARD, padx=12, pady=10)
        body.pack(fill="both", expand=True)

        self.text = tk.Text(body, wrap="none", height=12, width=40, font=self.f_mono, bg="#FFFFFF", fg="#202124",
                            relief="flat", padx=10, pady=8, insertwidth=0,
                            highlightthickness=1, highlightbackground=COLOR_BORDER,
                            tabs=("2c",), spacing1=1, spacing3=1)
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._config_tags()
        self.text.configure(state="disabled")

    def _work_area(self) -> tuple:
        """返回桌面可用区域（排除任务栏），拿不到时退回整屏。"""
        if sys.platform == "win32":
            try:
                import ctypes
                import ctypes.wintypes
                rect = ctypes.wintypes.RECT()
                # SPI_GETWORKAREA = 0x0030
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    if rect.right > rect.left and rect.bottom > rect.top:
                        return rect.left, rect.top, rect.right, rect.bottom
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _fit_window(self) -> None:
        """按内容与桌面可用区域自适应窗口尺寸，避免被任务栏或屏幕边缘遮挡。"""
        self.root.update_idletasks()
        k = self.ui_scale
        wl, wt, wr, wb = self._work_area()
        avail_w = max(wr - wl, int(640 * k))
        avail_h = max(wb - wt, int(460 * k))

        w = min(max(self.root.winfo_reqwidth(), int(1000 * k)), avail_w - int(16 * k))
        h = min(max(self.root.winfo_reqheight(), int(720 * k)), avail_h - int(16 * k))
        x = wl + max((avail_w - w) // 2, 0)
        y = wt + max((avail_h - h) // 4, 0)
        self.root.geometry("{}x{}+{}+{}".format(int(w), int(h), int(x), int(y)))
        self.root.minsize(min(int(820 * k), int(w)), min(int(500 * k), int(h)))

        # 客户区高度不含标题栏，可能仍顶到任务栏；按标题栏实际高度精确修正
        self.root.update_idletasks()
        max_h = (wb - int(18 * k)) - self.root.winfo_rooty()
        if 0 < max_h < self.root.winfo_height():
            self.root.geometry("{}x{}".format(int(w), int(max_h)))

    def _config_tags(self) -> None:
        self.text.tag_configure("title", foreground=COLOR_TITLE, font=(self.f_ui[0], 11, "bold"),
                                spacing1=2, spacing3=6)
        self.text.tag_configure("section", foreground=COLOR_SECTION,
                                font=(self.f_ui[0], 10, "bold"), spacing1=10, spacing3=4)
        self.text.tag_configure("kv", foreground="#202124")
        # 域段值无法解析（保留编码 / 未定义 / 缺表）时整行标红
        self.text.tag_configure("err", foreground=COLOR_WARN, background=COLOR_ERR_BG)
        self.text.tag_configure("text", foreground=COLOR_TEXT)
        self.text.tag_configure("warn", foreground=COLOR_WARN)
        self.text.tag_configure("good", foreground=COLOR_GOOD)
        self.text.tag_configure("blank", spacing1=0)

    # ------------------------------------------------------------ 事件
    def _on_key(self, event=None) -> None:
        if event is not None and event.keysym == "Return":
            self._parse_now()
            return
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.root.after(260, self._parse_now)

    def _on_paste(self, event) -> None:
        # 粘贴整行时（含空格）分发到 4 个输入框
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        tokens = [t for t in re.split(r"[\s,;]+", text.strip()) if t]
        if len(tokens) >= 2 and all(re.fullmatch(r"(0[xX])?[0-9a-fA-F]{1,8}", t) for t in tokens):
            for i in range(4):
                self.dw_vars[i].set(tokens[i] if i < len(tokens) else "")
            self.root.after(30, self._parse_now)
            return "break"
        return None

    def _on_change(self) -> None:
        self._parse_now()

    def _load_sample(self) -> None:
        sample = SAMPLE_FM if self.mode_var.get() == MODE_FM else SAMPLE_NFM
        for i, v in enumerate(sample):
            self.dw_vars[i].set(v)
        self._parse_now()

    def _clear(self) -> None:
        for v in self.dw_vars:
            v.set("")
        self._render_lines([])
        self.status.configure(text="")

    # ------------------------------------------------------------ 输入解析
    def _collect(self) -> List[int]:
        """把 4 个输入框整理成 (值, 是否有输入) 列表。"""
        values: List[int] = []
        for i, var in enumerate(self.dw_vars):
            raw = var.get().strip()
            if not raw:
                values.append(0)
                continue
            tokens = [t for t in re.split(r"[\s,;]+", raw) if t]
            if len(tokens) > 1:
                raise ValueError("DW{} 里出现了多个值，请分到各自的框里".format(i))
            s = tokens[0]
            if s.lower().startswith("0x"):
                s = s[2:]
            if not re.fullmatch(r"[0-9a-fA-F]{1,8}", s):
                raise ValueError("DW{} 不是合法的十六进制（1~8 位）".format(i))
            values.append(int(s, 16))
        return values

    def _parse_now(self) -> None:
        self._after_id = None
        try:
            values = self._collect()
        except ValueError as exc:
            self.status.configure(text=str(exc), fg=COLOR_WARN)
            return

        if not any(var.get().strip() for var in self.dw_vars):
            self._render_lines([])
            self.status.configure(text="请输入 TLP Header 数据", fg=COLOR_HINT)
            return

        provided_dw = 4
        while provided_dw > 1 and values[provided_dw - 1] == 0 and not self.dw_vars[provided_dw - 1].get().strip():
            provided_dw -= 1

        data: List[int] = []
        for v in values:
            data.extend([(v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])

        mode = "fm" if self.mode_var.get() == MODE_FM else "nfm"
        result = parse(data, mode, provided_dw=provided_dw)
        self._render_lines(result.lines)
        self._update_status(result, values, provided_dw)

    def _update_status(self, result: ParseResult, values: List[int], provided_dw: int) -> None:
        if result.error_count:
            self.status.configure(text="{}（已标红）".format(result.summary), fg=COLOR_WARN)
        else:
            self.status.configure(
                text="{}  ·  输入 {} DW".format(result.summary, provided_dw), fg=COLOR_HINT)

    # ------------------------------------------------------------ 渲染
    def _render_lines(self, lines: List[Line]) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if not lines:
            self.text.insert("end", "等待输入……", "text")
        for line in lines:
            self.text.insert("end", line.text + "\n", line.kind)
        self.text.configure(state="disabled")
        self.text.see("1.0")


def _enable_dpi_awareness() -> None:
    """Windows 上声明 DPI 感知，避免系统把窗口位图拉伸导致字体发虚。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
    except ImportError:  # pragma: no cover
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System DPI aware
    except Exception:  # pragma: no cover - Win7 或已设置过
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _resource_path(rel: str) -> str:
    """兼容 PyInstaller 单文件模式（资源解压到 sys._MEIPASS）。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), rel)


def create_root() -> tk.Tk:
    """创建已配置好 DPI、缩放与图标的根窗口。"""
    _enable_dpi_awareness()
    root = tk.Tk()

    # 按真实 DPI 设置缩放，保证不同屏幕上字体物理尺寸一致
    dpi = 96.0
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        pass
    if dpi <= 0:
        dpi = 96.0
    try:
        root.call("tk", "scaling", max(1.0, min(dpi / 72.0, 4.0)))
    except tk.TclError:
        pass

    icon = _resource_path(os.path.join("assets", "app.ico"))
    if os.path.isfile(icon):
        try:
            root.iconbitmap(default=icon)
        except tk.TclError:
            pass
    return root


def main() -> None:
    root = create_root()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
