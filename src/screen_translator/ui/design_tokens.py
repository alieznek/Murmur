"""Murmur: warm-paper colors and typography for native Qt windows."""
from dataclasses import dataclass


PRIMITIVES = {
    "white": "#ffffff", "ink": "#54443c", "slate": "#846a58", "mist": "#faf7f1",
    "line": "#e9e0d5", "blue": "#bd684b", "blue_hover": "#a7563c", "blue_tint": "#efe5d5",
    "night": "#342b25", "night_panel": "#3c3027", "night_line": "#69503c",
    "night_text": "#e4d8c9", "night_muted": "#baa18d", "night_blue": "#dfac89",
}


@dataclass(frozen=True)
class Theme:
    canvas: str
    panel: str
    text: str
    muted: str
    border: str
    control_border: str
    accent: str
    action: str
    action_hover: str
    soft: str
    hover: str
    disabled: str
    disabled_text: str
    selection: str


LIGHT = Theme(PRIMITIVES["mist"], "#fffdf8", PRIMITIVES["ink"], PRIMITIVES["slate"],
              PRIMITIVES["line"], "#dfcfbd", PRIMITIVES["blue"], "#b45d40",
              PRIMITIVES["blue_hover"], PRIMITIVES["blue_tint"], "#f2e8db", "#eee4d6", "#b29f8c", "#efd1b7")
DARK = Theme(PRIMITIVES["night"], PRIMITIVES["night_panel"], PRIMITIVES["night_text"],
             PRIMITIVES["night_muted"], PRIMITIVES["night_line"], "#687b96", PRIMITIVES["night_blue"],
             "#b45d40", "#c0714f", "#53402e", "#5b412b", "#473529", "#9e8572", "#765035")

COMPONENT = {"control_height": 30, "radius": 8, "card_radius": 20, "icon": 16,
             "gutter": 28, "gap": 9, "toolbar_height": 78, "reading_size": 27}


def theme_for(name: str = "light") -> Theme:
    return DARK if name == "dark" else LIGHT
