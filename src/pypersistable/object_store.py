import datetime as dt
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, TypeVar

T = TypeVar("T")


class ObjectStore(Protocol[T]):
    def read(
        self,
        object_ids: Iterable[Path],
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
    ) -> dict[Path, T]: ...

    def write(
        self,
        objects: Iterable[T],
        effective_time: dt.datetime = dt.datetime.max,
        check: bool = True,
        by_reference: bool = True,
    ): ...