import asyncio
import datetime as dt
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Self, TypeVar

T = TypeVar("T")


class UnknownObjectError(KeyError):
    def __init__(self, typ: type, kwargs: dict[str, Any], object_id: Path):
        self.typ = typ
        self.kwargs = kwargs
        self.object_id = object_id
        super().__init__(f"Unknown object {object_id}")

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.kwargs.items())
        return f"No object found for {self.typ.__qualname__}({args}) [{self.object_id}]"


class ObjectStore:
    def read(
        self,
        object_ids: Iterable[Path],
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
    ) -> dict[Path, Any]: ...

    def write(
        self,
        objects: Iterable[Any],
        effective_time: dt.datetime = dt.datetime.max,
        check: bool = True,
        by_reference: bool = True,
    ): ...


@dataclass(frozen=True)
class _ReadKey:
    db_id: int
    effective_time: dt.datetime
    entry_time: dt.datetime


class ReadBatch:
    __current: ClassVar[ContextVar[Self | None]] = ContextVar(
        "ReadBatch.current", default=None
    )

    def __init__(self):
        self.__pending: dict[_ReadKey, tuple[ObjectStore, set[Path]]] = {}
        self.__tasks: dict[_ReadKey, asyncio.Future[dict[Path, Any]]] | None = None

    @classmethod
    def current(cls) -> Self:
        if (current := cls.__current.get()) is None:
            current = cls()
            cls.__current.set(current)
        return current

    @property
    def dispatched(self) -> bool:
        return self.__tasks is not None

    def dispatch(self):
        if self.dispatched:
            return

        self.__tasks = {
            db_id: asyncio.ensure_future(asyncio.to_thread(db.read, object_ids))
            for db_id, (db, object_ids) in self.__pending.items()
        }

    def enqueue(
        self,
        db: ObjectStore,
        typ: type,
        object_id: Path,
        kwargs: dict[str, Any],
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
    ):
        if self.dispatched:
            raise RuntimeError("Cannot enqueue after dispatch")

        key = _ReadKey(id(db), effective_time, entry_time)
        self.__pending.setdefault(key, (db, set()))[1].add(object_id)
        return self.__result(key, typ, object_id, dict(kwargs))

    async def __result(
        self, key: _ReadKey, typ: type, object_id: Path, kwargs: dict[str, Any]
    ) -> Any:
        self.dispatch()
        assert self.__tasks is not None

        results = await self.__tasks[key]

        try:
            value = results.pop(object_id)
            if not results:
                self.__tasks.pop(key)
                if not self.__tasks:
                    self.__tasks = None

            return value
        except KeyError:
            raise UnknownObjectError(typ, kwargs, object_id) from None
