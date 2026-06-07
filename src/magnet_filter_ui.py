"""Desktop UI for configuring magnet filter priority rules."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from src.bridge_server import bridge_server
from src.magnet_filter_store import (
    CODE_PLACEHOLDER,
    DEFAULT_TXT_SCREEN_STAGES,
    PREVIEW_KEYWORDS,
    PREVIEW_SINGLE_MP4,
    PRIORITY_COUNT,
    TXT_STAGE_4K,
    TXT_STAGE_HD,
    TXT_STAGE_SUBTITLE,
    VALID_TXT_STAGES,
    load_magnet_filter_rules,
    save_magnet_filter_rules,
)

TXT_STAGE_OPTIONS = [
    (TXT_STAGE_4K, "4K 筛查"),
    (TXT_STAGE_SUBTITLE, "字幕筛查（优先级1–4）"),
    (TXT_STAGE_HD, "高清筛查（优先级5–8）"),
]
TXT_STAGE_LABELS = dict(TXT_STAGE_OPTIONS)


class MagnetFilterRulesWindow(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk) -> None:
        super().__init__(master)
        self.title("磁链筛选规则")
        self.geometry("920x640")
        self.minsize(820, 560)
        self.transient(master)
        self.grab_set()

        self._rule_widgets: list[dict] = []
        self._build_ui()
        self._load_into_form(load_magnet_filter_rules())

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="生成 TXT 三阶段筛查（顺序可调整，默认 4K → 字幕 → 高清）",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        stage_frame = ctk.CTkFrame(header, fg_color="transparent")
        stage_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._stage_vars: list[tk.StringVar] = []
        for index in range(3):
            ctk.CTkLabel(stage_frame, text=f"第 {index + 1} 步", width=56, anchor="w").grid(
                row=0, column=index * 2, sticky="w", padx=(0, 6)
            )
            var = tk.StringVar(value=DEFAULT_TXT_SCREEN_STAGES[index])
            menu = ctk.CTkOptionMenu(
                stage_frame,
                variable=var,
                values=[label for _, label in TXT_STAGE_OPTIONS],
                width=220,
            )
            menu.grid(row=0, column=index * 2 + 1, sticky="w", padx=(0, 12))
            self._stage_vars.append(var)

        ctk.CTkLabel(
            header,
            text=(
                "① 4K 筛查：先看 JavDB 详情页磁链区，再看 18mag，匹配 4K/2160p/UHD 名称。"
                "② 字幕筛查：18mag 按优先级 1–4 查找，无则回退 JavDB 磁链区。"
                "③ 高清筛查：18mag 按优先级 5–8 查找，无则回退 JavDB 磁链区；仍无则生成「无合适资源」空 TXT。"
                "占位符：{CODE} 与 {code} 等价，番号字母大小写不敏感；名称须完整匹配。"
                "预览关键词模式：全部预览文件名均参与匹配（含 .mp4 / .url 等）；"
                "匹配时忽略空格（最 新=最新，斗鱼 体育=斗鱼体育），须为连续子串（「最新」可匹配「最新电影抢先看」/「最 新 电 影 抢 先 看」）。"
                "全局排除 / 列表隐藏关键词请用分号分隔。"
            ),
            anchor="w",
            justify="left",
            wraplength=860,
            text_color=("gray25", "gray75"),
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

        global_frame = ctk.CTkFrame(self)
        global_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        global_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            global_frame,
            text="全局排除关键词（名称与预览均参与；分号分隔。生成 TXT 时若已命中预览关键词，仅检查含该关键词的文件是否含排除词）",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        self.reject_text = ctk.CTkTextbox(global_frame, height=70)
        self.reject_text.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ctk.CTkLabel(
            global_frame,
            text="列表显示隐藏关键词（磁链名称与预览内容均参与；分号分隔，如 斗鱼;合集）",
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 4))
        self.display_hide_text = ctk.CTkTextbox(global_frame, height=60)
        self.display_hide_text.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))

        highlight_frame = ctk.CTkFrame(global_frame, fg_color="transparent")
        highlight_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        highlight_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(highlight_frame, text="列表显示着色", width=120, anchor="w").grid(
            row=0, column=0, sticky="nw", padx=(0, 8)
        )
        self.highlight_text = ctk.CTkTextbox(highlight_frame, height=72)
        self.highlight_text.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(
            highlight_frame,
            text="每行或多条用分号分隔：关键词|颜色，例如 4K|#dc2626;-C|#2563eb；同一行多个关键词用英文逗号",
            anchor="w",
            text_color=("gray25", "gray75"),
        ).grid(row=1, column=1, sticky="w", pady=(4, 0))

        scroll = ctk.CTkScrollableFrame(self, label_text="优先级规则（1 = 最高）")
        scroll.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        scroll.grid_columnconfigure(0, weight=1)

        for priority in range(1, PRIORITY_COUNT + 1):
            block = ctk.CTkFrame(scroll)
            block.grid(row=priority - 1, column=0, sticky="ew", pady=6)
            block.grid_columnconfigure(1, weight=1)

            enabled_var = tk.BooleanVar(value=False)
            ctk.CTkCheckBox(block, text=f"优先级 {priority}", variable=enabled_var).grid(
                row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4)
            )

            ctk.CTkLabel(block, text="磁链名称", width=90, anchor="w").grid(
                row=1, column=0, sticky="w", padx=8, pady=4
            )
            name_entry = ctk.CTkEntry(block, placeholder_text=f"例: {CODE_PLACEHOLDER}-C")
            name_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=4)

            preview_var = tk.StringVar(value=PREVIEW_KEYWORDS)
            mode_frame = ctk.CTkFrame(block, fg_color="transparent")
            mode_frame.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=2)
            ctk.CTkRadioButton(
                mode_frame,
                text="预览：包含关键词",
                variable=preview_var,
                value=PREVIEW_KEYWORDS,
                command=lambda p=priority - 1: self._refresh_mode_state(p),
            ).pack(side="left", padx=(0, 12))
            ctk.CTkRadioButton(
                mode_frame,
                text="预览：仅含一个 .mp4",
                variable=preview_var,
                value=PREVIEW_SINGLE_MP4,
                command=lambda p=priority - 1: self._refresh_mode_state(p),
            ).pack(side="left")

            ctk.CTkLabel(block, text="预览关键词", width=90, anchor="w").grid(
                row=3, column=0, sticky="nw", padx=8, pady=(4, 8)
            )
            keywords_text = ctk.CTkTextbox(block, height=52)
            keywords_text.grid(row=3, column=1, sticky="ew", padx=8, pady=(4, 8))

            self._rule_widgets.append(
                {
                    "priority": priority,
                    "enabled_var": enabled_var,
                    "name_entry": name_entry,
                    "preview_var": preview_var,
                    "keywords_text": keywords_text,
                }
            )

        footer = ctk.CTkFrame(self)
        footer.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 12))
        ctk.CTkButton(footer, text="保存并同步到扩展", command=self._on_save).pack(side="left", padx=6)
        ctk.CTkButton(footer, text="关闭", command=self.destroy).pack(side="right", padx=6)

    def _refresh_mode_state(self, index: int) -> None:
        widgets = self._rule_widgets[index]
        is_keywords = widgets["preview_var"].get() == PREVIEW_KEYWORDS
        widgets["keywords_text"].configure(state="normal" if is_keywords else "disabled")

    def _load_into_form(self, data: dict) -> None:
        reject_lines = ";".join(data.get("reject_keywords") or [])
        self.reject_text.delete("1.0", "end")
        self.reject_text.insert("1.0", reject_lines)

        hide_lines = ";".join(data.get("display_hide_keywords") or [])
        self.display_hide_text.delete("1.0", "end")
        self.display_hide_text.insert("1.0", hide_lines)

        highlight_lines = []
        for rule in data.get("display_highlight_rules") or []:
            if not isinstance(rule, dict):
                continue
            keywords = rule.get("keywords") or []
            if isinstance(keywords, str):
                kw_text = keywords
            else:
                kw_text = ",".join(str(k) for k in keywords if str(k).strip())
            color = str(rule.get("color", "#dc2626")).strip() or "#dc2626"
            if kw_text:
                highlight_lines.append(f"{kw_text}|{color}")
        self.highlight_text.delete("1.0", "end")
        self.highlight_text.insert("1.0", "\n".join(highlight_lines))

        stages = data.get("txt_screen_stages") or list(DEFAULT_TXT_SCREEN_STAGES)
        for index, var in enumerate(self._stage_vars):
            stage = stages[index] if index < len(stages) else DEFAULT_TXT_SCREEN_STAGES[index]
            var.set(TXT_STAGE_LABELS.get(stage, TXT_STAGE_LABELS[DEFAULT_TXT_SCREEN_STAGES[index]]))

        priorities = data.get("priorities") or []
        for idx, widgets in enumerate(self._rule_widgets):
            rule = priorities[idx] if idx < len(priorities) else {}
            widgets["enabled_var"].set(bool(rule.get("enabled")))
            widgets["name_entry"].delete(0, "end")
            widgets["name_entry"].insert(0, str(rule.get("name_pattern", "")))
            widgets["preview_var"].set(
                rule.get("preview_mode", PREVIEW_KEYWORDS)
                if rule.get("preview_mode") in (PREVIEW_KEYWORDS, PREVIEW_SINGLE_MP4)
                else PREVIEW_KEYWORDS
            )
            widgets["keywords_text"].delete("1.0", "end")
            widgets["keywords_text"].insert("1.0", "\n".join(rule.get("preview_keywords") or []))
            self._refresh_mode_state(idx)

    def _split_highlight_lines(self, raw: str) -> list[str]:
        lines: list[str] = []
        for line in raw.replace(",", "\n").splitlines():
            text = line.strip()
            if not text:
                continue
            if ";" in text and "|" in text:
                parts = [part.strip() for part in text.split(";") if part.strip() and "|" in part]
                if parts:
                    lines.extend(parts)
                    continue
            lines.append(text)
        return lines

    def _parse_highlight_rules(self, raw: str) -> list[dict]:
        rules: list[dict] = []
        for index, line in enumerate(self._split_highlight_lines(raw)):
            text = line.strip()
            if not text or "|" not in text:
                continue
            kw_part, color = text.split("|", 1)
            keywords = [k.strip() for k in kw_part.split(",") if k.strip()]
            if not keywords:
                continue
            rules.append(
                {
                    "id": index + 1,
                    "enabled": True,
                    "keywords": keywords,
                    "color": color.strip() or "#dc2626",
                }
            )
        return rules

    def _parse_txt_screen_stages(self) -> list[str]:
        label_to_stage = {label: stage for stage, label in TXT_STAGE_OPTIONS}
        stages: list[str] = []
        for var in self._stage_vars:
            stage = label_to_stage.get(var.get().strip())
            if stage and stage not in stages:
                stages.append(stage)
        for stage in DEFAULT_TXT_SCREEN_STAGES:
            if stage not in stages:
                stages.append(stage)
        return stages

    def _collect_form(self) -> dict:
        reject_raw = self.reject_text.get("1.0", "end").strip()
        reject_keywords = [part.strip() for part in reject_raw.split(";") if part.strip()]

        hide_raw = self.display_hide_text.get("1.0", "end").strip()
        display_hide_keywords = [part.strip() for part in hide_raw.split(";") if part.strip()]

        highlight_raw = self.highlight_text.get("1.0", "end").strip()
        display_highlight_rules = self._parse_highlight_rules(highlight_raw)

        priorities = []
        for widgets in self._rule_widgets:
            keywords_raw = widgets["keywords_text"].get("1.0", "end").strip()
            preview_keywords = [
                line.strip() for line in keywords_raw.replace(",", "\n").splitlines() if line.strip()
            ]
            priorities.append(
                {
                    "priority": widgets["priority"],
                    "enabled": widgets["enabled_var"].get(),
                    "name_pattern": widgets["name_entry"].get().strip(),
                    "preview_mode": widgets["preview_var"].get(),
                    "preview_keywords": preview_keywords,
                }
            )

        return {
            "version": 1,
            "reject_keywords": reject_keywords,
            "display_hide_keywords": display_hide_keywords,
            "display_highlight_rules": display_highlight_rules,
            "priorities": priorities,
            "txt_screen_stages": self._parse_txt_screen_stages(),
        }

    def _validate(self, data: dict) -> str | None:
        enabled = [r for r in data["priorities"] if r.get("enabled")]
        if not enabled:
            return "请至少启用并配置一条优先级规则。"

        for rule in enabled:
            if not rule.get("name_pattern"):
                return f"优先级 {rule['priority']} 未填写磁链名称模式。"
            mode = rule.get("preview_mode")
            if mode == PREVIEW_KEYWORDS and not rule.get("preview_keywords"):
                return f"优先级 {rule['priority']}：关键词模式下须填写至少一个预览关键词。"

        stages = data.get("txt_screen_stages") or []
        if len(set(stages)) != len(VALID_TXT_STAGES):
            return "TXT 三阶段筛查顺序不能重复，须包含 4K、字幕、高清各一次。"
        return None

    def _on_save(self) -> None:
        data = self._collect_form()
        error = self._validate(data)
        if error:
            messagebox.showerror("无法保存", error, parent=self)
            return
        save_magnet_filter_rules(data)
        bridge_server.broadcast_magnet_filter_rules()
        messagebox.showinfo("已保存", "磁链筛选规则已保存，并已推送到已连接的浏览器扩展。", parent=self)


def open_magnet_filter_rules_window(master: ctk.CTk) -> None:
    if getattr(master, "_magnet_filter_window", None) is not None:
        win = master._magnet_filter_window
        if win.winfo_exists():
            win.focus()
            return
    win = MagnetFilterRulesWindow(master)
    master._magnet_filter_window = win

    def _clear_ref() -> None:
        master._magnet_filter_window = None

    win.protocol("WM_DELETE_WINDOW", lambda: (win.destroy(), _clear_ref()))
