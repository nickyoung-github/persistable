from typing import Annotated, Any, Union, _SpecialForm

from pydantic import (
    BeforeValidator,
    Discriminator,
    GetJsonSchemaHandler,
    SerializationInfo,
    Tag,
    WrapSerializer,
)
from pydantic_core import CoreSchema


class _TagJsonSchema:
    def __init__(
        self,
        tag_field: str = "",
        tag_value: str = "",
    ):
        self.__tag_field = tag_field
        self.__tag_value = tag_value

    def __get_pydantic_json_schema__(
        self, schema: CoreSchema, handler: GetJsonSchemaHandler
    ):
        json_schema = handler(schema)
        resolved = dict(handler.resolve_ref_schema(json_schema))
        properties = resolved["properties"] = dict(resolved.get("properties", {}))
        required = resolved["required"] = list(resolved.setdefault("required", []))
        
        properties[self.__tag_field] = {"const": self.__tag_value}
        if self.__tag_field not in required:
            required.append(self.__tag_field)
            
        return resolved
    
        
@_SpecialForm # pyright: ignore[reportCallIssue]
def DiscriminatedUnion(_, params: tuple[type, ...]):
    # It would be nicer to use a class with __class_getitem__, but that does not play
    # nicely with static type checkers like pyright
    
    if not isinstance(params, tuple | list) or len(params) < 2:
        raise TypeError("Can only use with multiple types")

    tag_field = "__discriminator_type"  # Should not clash with any actual field names

    def strip_tag(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if k != tag_field}
        return value
    
    def discriminate(value: Any) -> str | None:
        if isinstance(value, dict):
            return value[tag_field]
        elif isinstance(value, params):
            typ = type(value)
            return f"{typ.__module__}:{typ.__qualname__}"
        return None
        
    def serialise(value: Any, handler: Any, info: SerializationInfo) -> Any:
        data = handler(value)
        if isinstance(data, dict):
            typ = type(value)
            return {tag_field: f"{typ.__module__}:{typ.__qualname__}", **data}
        return data

    union_members = tuple(
        Annotated[
            t,
            BeforeValidator(strip_tag),
            Tag(f"{t.__module__}:{t.__qualname__}"),
            _TagJsonSchema(tag_field, f"{t.__module__}:{t.__qualname__}")
        ]
        for t in params
    )

    return Annotated[
        Union[union_members],  # noqa: UP007
        WrapSerializer(serialise),
        Discriminator(discriminate)
    ]
