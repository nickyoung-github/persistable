import datetime as dt
from abc import abstractmethod
from collections.abc import Coroutine
from hashlib import sha512
from pathlib import Path
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Self,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from orjson import OPT_SORT_KEYS, dumps
from pydantic import TypeAdapter

from .object_store import ObjectStore, ReadBatch, UnknownObjectError
from .type_registry import TypeRegistry
from .typed_cache import typed_cache


class _IdFieldIndicator: ...


T = TypeVar("T")
IdField = Annotated[T, _IdFieldIndicator]


class Persistable:
    def __hash__(self):
        return int(self.object_id.name, 16)

    @classmethod
    @abstractmethod
    def id_fields(cls) -> set[str]: ...

    @classmethod
    def make_object_id(cls, **kwargs) -> Path:
        # ToDo: Is there any type hinting magic we can do here to give us the signature of the
        #       id fields? Not in the current iterations of python, without codegen?
        id_fields = cls.id_fields()
        if set(kwargs.keys()) != id_fields:
            raise RuntimeError("Must supply id fields only")

        values = TypeAdapter(dict).dump_python(kwargs, mode="json")
        payload = dumps(values, option=OPT_SORT_KEYS)
        name = sha512(payload).hexdigest()

        return Path(TypeRegistry[Self]().registered_name(cls)).joinpath(name)

    @overload
    @classmethod
    def read(
        cls,
        db: ObjectStore,
        *,
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
        is_async: Literal[False] = False,
        **kwargs,
    ) -> Self: ...

    @overload
    @classmethod
    def read(
        cls,
        db: ObjectStore,
        *,
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
        is_async: Literal[True],
        **kwargs,
    ) -> Coroutine[Any, Any, Self]: ...

    @classmethod
    def read(
        cls,
        db: ObjectStore,
        *,
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
        is_async: bool = False,
        **kwargs,
    ) -> Self | Coroutine[Any, Any, Self]:
        object_id = cls.make_object_id(**kwargs)
        if is_async:
            return ReadBatch.current().enqueue(
                db, cls, object_id, kwargs, effective_time, entry_time
            )

        try:
            return db.read([object_id], effective_time, entry_time)[object_id]
        except KeyError:
            raise UnknownObjectError(cls, kwargs, object_id) from None

    @property
    def object_id(self) -> Path:
        values = {f: getattr(self, f) for f in self.id_fields()}
        return self.make_object_id(**values)

    def write(self, db: ObjectStore):
        db.write([self])


class Identifiable(Persistable):
    def __init_subclass__(cls, **kwargs):
        if not cls.id_fields():
            raise TypeError(f"{cls!r} does not define any id fields")

    @classmethod
    @typed_cache
    def id_fields(cls) -> set[str]:
        return {
            name
            for name, hint in get_type_hints(cls, include_extras=True).items()
            if get_origin(hint) is Annotated and _IdFieldIndicator in get_args(hint)
        }


class Unique(Persistable):
    @classmethod
    @typed_cache
    def id_fields(cls) -> set[str]:
        return {
            name
            for name, hint in get_type_hints(cls)
            if get_origin(hint) is not ClassVar
        }
