import datetime as dt
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from pypersistable import (
    DiscriminatedUnion,
    Identifiable,
    IdField,
    Reference,
    TypeRegistry,
    Unique,
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
    counterparty: IdField[Counterparty]
    sales_coverage: tuple[str, ...]
    
__registry.register("CustomerBook", CustomerBook)

    
    
@dataclass(kw_only=True)
class TradingBook(Identifiable):
    name: IdField[str]
    owner: str
    
__registry.register("TradingBook", TradingBook)

    
@dataclass(kw_only=True)
class Option(Unique):
    ticker: str
    strike: float
    maturity: dt.datetime
    
__registry.register("Option", Option, Path("Instrument"))

Instrument = DiscriminatedUnion[__registry.types_for_root(Path("Instrument"))]


class TradeAction(StrEnum):
    Buy = auto()
    Sell = auto()
    Pay = auto()
    Receive = auto()
    
 
@dataclass(kw_only=True)
class Position(Unique):
    quantity: float
    action: TradeAction
    instrument: Reference[Instrument] # pyright: ignore[reportInvalidTypeForm]

__registry.register("Position", Position)


@dataclass(kw_only=True)
class Deal(Identifiable):
    deal_id: IdField[str]
    book_from: Reference[TradingBook]
    book_to: Reference[TradingBook | CustomerBook]
    position: list[Position]
    
__registry.register("Deal", Deal)
