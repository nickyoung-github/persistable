from dataclasses import dataclass  # noqa: N999

from pypersistable import (
    FSStore,
    FSStoreFormat,
    Identifiable,
    IdField,
    Reference,
    TypeRegistry,
)

__registry = TypeRegistry()


@dataclass(kw_only=True)
class Counterparty(Identifiable):
    name: IdField[str]
    location: str
    contact_name: str


__registry.register("Counterparty", Counterparty)


@dataclass(kw_only=True)
class CustomerBook(Identifiable):
    counterparty: IdField[Reference[Counterparty]]
    sales_coverage: tuple[str, ...]


__registry.register("CustomerBook", CustomerBook)


ctpy = Counterparty(name="Acme", location="NW3", contact_name="Nick")
book = CustomerBook(counterparty=ctpy, sales_coverage=("Tweedledum", "Tweedledee"))
root = r"file:///Users/Nick/ObjectStore"


for store_format in (FSStoreFormat.Json, FSStoreFormat.Parquet):
    store = FSStore(f"{root}/{store_format.name.lower()}", record_format=store_format)
    store.write([book])

    ctpy_id = Counterparty.make_object_id(name="Acme")
    ctpy_loaded = store.read([ctpy_id])[ctpy_id]
    print(f"({store_format!s}) Loaded counterparty: {ctpy_loaded}")
    print(
        f"({store_format!s})Loaded counterparty matches original: {ctpy_loaded == ctpy}\n"
    )

    book_id = CustomerBook.make_object_id(counterparty=ctpy_loaded)
    book_loaded = store.read([book_id])[book_id]
    print(f"({store_format!s})Loaded customer book: {book_loaded}")
    print(
        f"({store_format!s})Loaded customer book matches original: {book_loaded == book}\n"
    )
