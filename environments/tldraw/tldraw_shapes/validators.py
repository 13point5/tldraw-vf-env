import math
from typing import Annotated, Union

from pydantic import AfterValidator, BeforeValidator, StrictFloat, StrictInt


def _ensure_number(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected number")
    if not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return value


Number = Annotated[Union[StrictInt, StrictFloat], BeforeValidator(_ensure_number)]


def _ensure_non_zero_number(value: Union[int, float]) -> Union[int, float]:
    if value <= 0:
        raise ValueError("Expected a non-zero positive number")
    return value


NonZeroNumber = Annotated[Number, AfterValidator(_ensure_non_zero_number)]
