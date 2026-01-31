from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict


class RichText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    content: list[Any]
    attrs: Any | None = None


TLRichText: TypeAlias = RichText


def to_rich_text(text: str) -> RichText:
    lines = text.split("\n")
    content: list[dict[str, Any]] = []
    for line in lines:
        if line == "":
            content.append({"type": "paragraph"})
        else:
            content.append(
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            )

    return RichText(type="doc", content=content)
