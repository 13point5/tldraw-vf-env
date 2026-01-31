from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

from .styles import (
    TLDefaultColorStyle,
    TLDefaultDashStyle,
    TLDefaultFillStyle,
    TLDefaultFontStyle,
    TLDefaultHorizontalAlignStyle,
    TLDefaultSizeStyle,
    TLDefaultVerticalAlignStyle,
)
from .validators import LinkUrl, NonZeroNumber, PositiveNumber


GeoShapeGeoStyle: TypeAlias = Literal[
    "cloud",
    "rectangle",
    "ellipse",
    "triangle",
    "diamond",
    "pentagon",
    "hexagon",
    "octagon",
    "star",
    "rhombus",
    "rhombus-2",
    "oval",
    "trapezoid",
    "arrow-right",
    "arrow-left",
    "arrow-up",
    "arrow-down",
    "x-box",
    "check-box",
    "heart",
]


class GeoShapeProps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geo: GeoShapeGeoStyle = "rectangle"
    w: NonZeroNumber
    h: NonZeroNumber
    dash: TLDefaultDashStyle = "draw"
    url: LinkUrl = ""
    growY: PositiveNumber = 0
    scale: NonZeroNumber = 1
    labelColor: TLDefaultColorStyle = "black"
    color: TLDefaultColorStyle = "black"
    fill: TLDefaultFillStyle = "none"
    size: TLDefaultSizeStyle = "m"
    font: TLDefaultFontStyle = "draw"
    align: TLDefaultHorizontalAlignStyle = "middle"
    verticalAlign: TLDefaultVerticalAlignStyle = "middle"
    richText: str = ""


TLGeoShapeProps: TypeAlias = GeoShapeProps
