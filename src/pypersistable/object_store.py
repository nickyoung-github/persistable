import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, make_dataclass
from functools import cache
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import TypeAdapter

from .persistable import Persistable
from .type_registry import TypeRegistry

T = TypeVar("T", bound=type[Persistable])


class ObjectStore(Protocol):
    def read(
        self,
        object_ids: Iterable[Path],
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
    ) -> dict[Path, Persistable]: ...

    def write(
        self,
        objects: Iterable[Persistable],
        effective_time: dt.datetime = dt.datetime.max,
        check: bool = True,
        by_reference: bool = True,
    ): ...


class ReferenceResolver:
    def __init__(self, store: ObjectStore):
        self.__store = store
        self.__discovering = True
        self.__pending_reads: set[Path] = set()
        self.__pending_writes: dict[Path, Persistable] = {}
        self.__resolved: dict[Path, Persistable] = {}

    def get(self, object_id: Path):
        if object_id in self.__resolved:
            return self.__resolved[object_id]
        elif self.__discovering:
            self.__pending_reads.add(object_id)
            return str(object_id)
        raise RuntimeError("Failed to resolve {object_id")

    def write(self, obj: Persistable):
        self.__pending_writes[obj.object_id] = obj

    def take_pending_writes(self) -> tuple[Persistable, ...]:
        pending_writes = tuple(self.__pending_writes.values())
        self.__pending_writes = {}
        return pending_writes

    def resolve(self) -> bool:
        self.__discovering = False

        if not self.__pending_reads:
            return False

        loaded = self.__store.read(self.__pending_reads)
        if len(loaded) < len(self.__pending_reads):
            missing = self.__pending_reads.difference(loaded.keys())
            raise RuntimeError(f"Failed to load {missing!r}")

        self.__resolved.update(loaded)
        self.__pending_reads = set()

        return True


@dataclass
class MetaData:
    effective_time: dt.datetime
    entry_time: dt.datetime
    host: str
    user: str


@dataclass
class ObjectRecord[T]:  # There is a reason for this
    object_id: str
    metadata: MetaData
    data: T

    @property
    def registered_name(self) -> str:
        return str(Path(self.object_id).parent)


class ObjectStoreBase(ObjectStore):
    def _read(
        self,
        by_directory: dict[Path, list[Path]],
        effective_time: dt.datetime,
        entry_time: dt.datetime,
    ) -> dict[Path, list[dict[str, Any]]]: ...

    def _write(self, records_by_path: dict[Path, list[dict[str, Any]]]): ...

    @classmethod
    @cache
    def record_type(cls, typ: type[Persistable]) -> type[ObjectRecord]:
        record_typ = make_dataclass(
            f"{typ.__qualname__}Record",
            fields=[
                ("data", typ),
            ],
            bases=(ObjectRecord,),
        )
        return record_typ

    @classmethod
    @cache
    def type_adaptor(cls, typ: type[ObjectRecord]) -> TypeAdapter[ObjectRecord]:
        return TypeAdapter(typ)

    @classmethod
    def type_registry(cls) -> TypeRegistry[Persistable]:
        return TypeRegistry[Persistable]()

    def read(
        self,
        object_ids: Iterable[Path],
        effective_time: dt.datetime = dt.datetime.max,
        entry_time: dt.datetime = dt.datetime.max,
    ) -> dict[Path, Persistable]:
        # Group the reads by directory, handle deserialisation, and resolve references

        ret: dict[Path, Persistable] = {}
        by_directory: dict[Path, list[Path]] = {}
        resolver_cache: dict[Path, Persistable] = {}
        type_registry = self.type_registry()

        for oid in object_ids:
            # oid.parent is the registered_name
            if oid in resolver_cache:
                ret[oid] = resolver_cache[oid]
                continue

            typ = type_registry.get_type(str(oid.parent))
            directory = type_registry.root(typ).joinpath(oid.parent)
            by_directory.setdefault(directory, []).append(oid)

        all_results = self._read(by_directory, effective_time, entry_time)
        for directory, results in all_results.items():
            if not results:
                continue

            typ = type_registry.get_type(Path(results[0]["object_id"]).parent.name)
            type_adaptor = self.type_adaptor(self.record_type(typ))

            for result in results:
                resolver = ReferenceResolver(self)
                context = {"resolver": resolver}
                record = type_adaptor.validate_python(result, context=context)

                if resolver.resolve():
                    record = type_adaptor.validate_python(result, context=context)

                object_id = Path(record.object_id)
                resolver_cache[object_id] = ret[object_id] = record.data

        return ret

    def write(
        self,
        objects: Iterable[Persistable],
        effective_time: dt.datetime = dt.datetime.max,
        check: bool = True,
        by_reference: bool = True,
    ):
        # Construct and serialise the object record, group records by path

        if check:
            current = self.read(o.object_id for o in objects)
            objects = [o for o in objects if current.get(o.object_id) != o]
        else:
            objects = list(objects)

        if not objects:
            return

        type_registry = self.type_registry()
        by_path: dict[Path, list[dict[str, Any]]] = {}
        entry_time = dt.datetime.now(dt.UTC)
        filename = Path(f"{entry_time.isoformat()}")
        metadata = MetaData(
            effective_time=effective_time
            if effective_time != dt.datetime.max
            else entry_time,
            entry_time=entry_time,
            host="nick-host",
            user="nick",
        )

        while objects:
            obj = objects.pop()
            object_id = obj.object_id
            typ = type(obj)
            directory = type_registry.root(typ).joinpath(object_id.parent)
            path = directory.joinpath(filename)
            record_type = self.record_type(typ)
            type_adapter = self.type_adaptor(record_type)
            record = record_type(
                object_id=str(object_id),
                metadata=metadata,
                data=obj,  # pyright: ignore[reportCallIssue]
            )
            resolver = ReferenceResolver(self)
            context = {"resolver": resolver} if by_reference else None
            data = type_adapter.dump_python(record, context=context)

            objects.extend(resolver.take_pending_writes())
            by_path.setdefault(path, []).append(data)

        self._write(by_path)
