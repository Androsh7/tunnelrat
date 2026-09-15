"""Defines help commands for models"""

# Standard libraries
import enum
import types
from typing import Union, get_args, get_origin

# Third-party libraries
from pydantic import BaseModel
from tabulate import tabulate

# Project libraries
from tunnelrat.constants import ALL_ENUMS


def format_type(annotation) -> str:
    origin = get_origin(annotation)

    # Union[int, str] and int | str
    if origin is Union or origin is types.UnionType:
        return " or ".join(format_type(a) for a in get_args(annotation))

    # Generics like list[int], dict[str, int]
    if origin is not None:
        args = ", ".join(format_type(a) for a in get_args(annotation))
        return f"{origin.__name__}[{args}]"

    if annotation is type(None):
        return "None"

    return getattr(annotation, "__name__", str(annotation))


def model_to_specification_table(model: type[BaseModel], title: str) -> str:
    rows = []
    for name, field_info in model.model_fields.items():
        default = "(required)" if field_info.is_required() else repr(field_info.default)
        rows.append([name, format_type(field_info.annotation), default, field_info.description or ""])
    table_string = tabulate(rows, headers=["name", "type", "default", "description"], tablefmt="pretty")
    table_lines = table_string.splitlines()
    border_line = table_lines[0]
    inner_width = len(border_line) - 2
    title_line = f"|{title.center(inner_width)}|"
    return "\n".join([border_line, title_line, *table_lines])

def format_enum_as_assignment(enum_class: type[enum.Enum]) -> str:
    return f"{enum_class.__name__} = {[member.value for member in enum_class]}"


def format_all_enums_as_assignments() -> str:
    return "Enums:\n" + "\n".join(f" - {format_enum_as_assignment(enum_class)}" for enum_class in ALL_ENUMS)
