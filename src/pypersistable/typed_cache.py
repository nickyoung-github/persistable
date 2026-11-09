from collections.abc import Callable
from functools import lru_cache
from typing import ParamSpec, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")

def typed_cache[**P, R](func: Callable[P, R], maxsize: int | None = None) -> Callable[P, R]:
    # Useful if you want to cache a derived or abstract property. Without this, pyright complains that the
    # return type of the cached function is not compatible with the property type.
    return cast(Callable[P, R], lru_cache(maxsize=maxsize)(func))
