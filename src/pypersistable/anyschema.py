from pathlib import Path
from types import NoneType

import narwhals as nw
from anyschema._dependencies import is_dataclass
from anyschema.adapters import dataclass_adapter
from anyschema.exceptions import UnsupportedDTypeError
from anyschema.parsers import (
    AnnotatedStep,
    ForwardRefStep,
    PyTypeStep,
    UnionTypeStep,
    make_pipeline,
)
from anyschema.parsers._base import ParserStep
from anyschema.parsers.annotated_types import AnnotatedTypesStep
from anyschema.parsers.pydantic import PydanticTypeStep
from anyschema.typing import FieldConstraints, FieldMetadata, FieldType
from narwhals.dtypes import DType

from .persistable import Persistable


class DataclassTypeStep(ParserStep):
    # anyschema can handle a dataclass passed as an argument to AnySchema,
    # however, it can't cope with nested dataclasses, so we need to add a step to handle them.

    def parse(
        self,
        input_type: FieldType,
        constraints: FieldConstraints,
        metadata: FieldMetadata,
    ) -> DType | None:
        if is_dataclass(input_type):
            return nw.Struct(
                [
                    nw.Field(
                        name=field_name,
                        dtype=self.pipeline.parse(
                            field_info, field_constraints, field_metadata, strict=True
                        ),
                    )
                    for field_name, field_info, field_constraints, field_metadata in dataclass_adapter(
                        input_type
                    )
                ]
            )



class _UnionTypeStep(UnionTypeStep):
    # References show up as a tuple of the underlying type and a Path. This is a hack to handle that.
    # Replacees the anyschema default UnionTypeStep.

    def _parse_union(self, union: tuple[FieldType, ...]) -> FieldType:
        if len(union) != 2:
            msg = "Union with more than two types is not supported."
            raise UnsupportedDTypeError(msg)

        field0, field1 = union

        if field0 is not NoneType and field1 is not NoneType:
            msg = "Union with mixed types is not supported."

            for f in (field0, field1):
                if (
                    f is not Path
                    and isinstance(f, type)
                    and not issubclass(f, Persistable)
                ):
                    raise UnsupportedDTypeError(msg)

            return str

        return field1 if field0 is NoneType else field0


# Construct our own pipeline, including our custom steps and excluding the default ones we don't care about,
# e.g., for attrs

PARSER_STEPS = (
    ForwardRefStep(),
    _UnionTypeStep(),
    AnnotatedStep(),
    AnnotatedTypesStep(),
    DataclassTypeStep(),
    PydanticTypeStep(),
    PyTypeStep(),
)

PIPELINE = make_pipeline(PARSER_STEPS)
