from typing import Literal, TypeAlias

DEFAULT_COLOR_NAMES = (
    "black",
    "grey",
    "light-violet",
    "violet",
    "blue",
    "light-blue",
    "yellow",
    "orange",
    "green",
    "light-green",
    "light-red",
    "red",
    "white",
)

TLDefaultColorStyle: TypeAlias = Literal[
    "black",
    "grey",
    "light-violet",
    "violet",
    "blue",
    "light-blue",
    "yellow",
    "orange",
    "green",
    "light-green",
    "light-red",
    "red",
    "white",
]

TLDefaultDashStyle: TypeAlias = Literal["draw", "solid", "dashed", "dotted"]

TLDefaultFillStyle: TypeAlias = Literal[
    "none",
    "semi",
    "solid",
    "pattern",
    "fill",
    "lined-fill",
]

TLDefaultFontStyle: TypeAlias = Literal["draw", "sans", "serif", "mono"]

TLDefaultHorizontalAlignStyle: TypeAlias = Literal[
    "start",
    "middle",
    "end",
    "start-legacy",
    "end-legacy",
    "middle-legacy",
]

TLDefaultVerticalAlignStyle: TypeAlias = Literal["start", "middle", "end"]

TLDefaultSizeStyle: TypeAlias = Literal["s", "m", "l", "xl"]
