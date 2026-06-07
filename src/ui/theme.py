"""JavDB-inspired colors and widget helpers for the desktop UI."""

from __future__ import annotations

import customtkinter as ctk

# JavDB accent orange
ACCENT = ("#ff7700", "#ff7700")
ACCENT_HOVER = ("#e56a00", "#e56a00")
ACCENT_SOFT = ("#fff3e6", "#3d2a14")

SURFACE = ("#ffffff", "#1e1e1e")
SURFACE_ALT = ("#f7f7f7", "#252525")
SURFACE_CARD = ("#fafafa", "#2a2a2a")
BORDER = ("#e8e8e8", "#3a3a3a")
TEXT = ("#222222", "#ececec")
TEXT_MUTED = ("#666666", "#a0a0a0")
HEADER_BG = ("#ffffff", "#181818")
STATUS_BG = ("#f3f3f3", "#141414")
SUCCESS = ("#15803d", "#4ade80")
WARNING = ("#b45309", "#fbbf24")
DANGER = ("#b91c1c", "#f87171")

# 影片库 tab — black shell, orange buttons, black typography on content wells
LIBRARY_BG = "#000000"
LIBRARY_PANEL = "#0a0a0a"
LIBRARY_CONTENT = "#f2f2f2"
LIBRARY_BORDER = "#333333"
LIBRARY_ACCENT = "#ff7700"
LIBRARY_ACCENT_HOVER = "#e56a00"
LIBRARY_TEXT = "#000000"
LIBRARY_TEXT_ON_DARK = "#f0f0f0"
LIBRARY_HEADING = "#ff7700"
LIBRARY_MUTED = "#888888"
LIBRARY_LINK = "#4da3ff"


def apply_app_theme() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")


def title_font(size: int = 16) -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight="bold")


def section_font(size: int = 13) -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight="bold")


def body_font(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(size=size)


def accent_button(master, **kwargs) -> ctk.CTkButton:
    opts = {
        "fg_color": ACCENT,
        "hover_color": ACCENT_HOVER,
        "text_color": ("#ffffff", "#ffffff"),
    }
    opts.update(kwargs)
    return ctk.CTkButton(master, **opts)


def ghost_button(master, **kwargs) -> ctk.CTkButton:
    opts = {
        "fg_color": "transparent",
        "border_width": 1,
        "border_color": BORDER,
        "hover_color": SURFACE_ALT,
        "text_color": TEXT,
    }
    opts.update(kwargs)
    return ctk.CTkButton(master, **opts)


def card_frame(master, **kwargs) -> ctk.CTkFrame:
    opts = {
        "corner_radius": 10,
        "border_width": 1,
        "border_color": BORDER,
        "fg_color": SURFACE_CARD,
    }
    opts.update(kwargs)
    return ctk.CTkFrame(master, **opts)


def style_tabview(tabview: ctk.CTkTabview) -> None:
    tabview.configure(
        segmented_button_fg_color=SURFACE_ALT,
        segmented_button_selected_color=ACCENT,
        segmented_button_selected_hover_color=ACCENT_HOVER,
        segmented_button_unselected_color=SURFACE_ALT,
        segmented_button_unselected_hover_color=BORDER,
        text_color=TEXT,
        text_color_disabled=TEXT_MUTED,
    )


def style_progress(progress: ctk.CTkProgressBar) -> None:
    progress.configure(
        progress_color=ACCENT,
        fg_color=BORDER,
        height=8,
        corner_radius=4,
    )


def library_accent_button(master, **kwargs) -> ctk.CTkButton:
    opts = {
        "fg_color": LIBRARY_ACCENT,
        "hover_color": LIBRARY_ACCENT_HOVER,
        "text_color": LIBRARY_TEXT,
    }
    opts.update(kwargs)
    return ctk.CTkButton(master, **opts)


def library_secondary_button(master, **kwargs) -> ctk.CTkButton:
    opts = {
        "fg_color": ("#d9d9d9", "#3a3a3a"),
        "hover_color": ("#cccccc", "#4a4a4a"),
        "text_color": LIBRARY_TEXT,
        "border_width": 0,
    }
    opts.update(kwargs)
    return ctk.CTkButton(master, **opts)


def library_wide_secondary_button(master, **kwargs) -> ctk.CTkButton:
    opts = {
        "fg_color": ("#d9d9d9", "#3a3a3a"),
        "hover_color": ("#cccccc", "#4a4a4a"),
        "text_color": LIBRARY_TEXT,
        "height": 32,
        "corner_radius": 6,
    }
    opts.update(kwargs)
    return ctk.CTkButton(master, **opts)


def library_card_frame(master, **kwargs) -> ctk.CTkFrame:
    opts = {
        "corner_radius": 10,
        "border_width": 1,
        "border_color": LIBRARY_BORDER,
        "fg_color": LIBRARY_BG,
    }
    opts.update(kwargs)
    return ctk.CTkFrame(master, **opts)
