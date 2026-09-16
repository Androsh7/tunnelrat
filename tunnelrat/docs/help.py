"""Defines help commands for models"""

# Standard libraries
import enum
import types
from importlib.resources import files
from typing import Any, Union, get_args, get_origin

# Third-party libraries
from pydantic import BaseModel
from tabulate import tabulate

# Project libraries
from tunnelrat.constants import (
    ALL_ENUMS,
    LOADER_INJECTED_KEY,
    MAX_DESCRIPTION_COLUMN_WIDTH,
    StepTypes,
)
from tunnelrat.script import STEP_TO_MODEL

EXAMPLE_SCRIPT_PACKAGE = "tunnelrat.docs"
EXAMPLE_SCRIPT_FILENAME = "example_script.yaml"


YAML_STRUCTURE = """Script structure:
steps:              # steps in order
  - <step type>:
      <step key>: <value>
"""


def format_type(annotation: Any) -> str:
    """Return a type annotation written the way a script author would read it

    Args:
        annotation: The annotation taken from a model field

    Returns:
        The name of the type, with unions joined by "or" and generics keeping their arguments
    """
    origin = get_origin(annotation)

    # Union[int, str] and int | str
    if origin is Union or origin is types.UnionType:
        return " or ".join(format_type(argument) for argument in get_args(annotation))

    # Generics like list[int], dict[str, int]
    if origin is not None:
        arguments = ", ".join(format_type(argument) for argument in get_args(annotation))
        return f"{origin.__name__}[{arguments}]"

    if annotation is type(None):
        return "None"

    return getattr(annotation, "__name__", str(annotation))


def is_loader_injected(field_info: Any) -> bool:
    """Return whether a field is filled in by the script loader instead of written in yaml

    Args:
        field_info: The field to check

    Returns:
        True if the field carries the loader injected marker
    """
    extra = field_info.json_schema_extra
    if not isinstance(extra, dict):
        return False
    return bool(extra.get(LOADER_INJECTED_KEY, False))


def model_to_specification_table(model: type[BaseModel], title: str) -> str:
    """Return the yaml keys of one model drawn as a titled table

    Args:
        model: The model to describe
        title: The heading to centre above the table

    Returns:
        A table of yaml key, type, default and description, with loader injected fields left out
    """
    rows = []
    for field_name, field_info in model.model_fields.items():
        if is_loader_injected(field_info):
            continue
        yaml_key = field_info.alias or field_name
        default = "(required)" if field_info.is_required() else repr(field_info.default)
        rows.append([yaml_key, format_type(field_info.annotation), default, field_info.description or ""])
    table_string = tabulate(
        rows,
        headers=["key", "type", "default", "description"],
        tablefmt="pretty",
        colalign=("left", "left", "left", "left"),
        maxcolwidths=[None, None, None, MAX_DESCRIPTION_COLUMN_WIDTH],
    )
    table_lines = table_string.splitlines()
    border_line = table_lines[0]
    inner_width = len(border_line) - 2
    title_line = f"|{title.center(inner_width)}|"
    return "\n".join([border_line, title_line, *table_lines])


def format_all_model_tables() -> str:
    """Return a table for every documented model, steps first and the host model last

    Returns:
        The tables separated by blank lines
    """
    return "\n\n".join(model_to_specification_table(model=model, title=name) for name, model in STEP_TO_MODEL.items())


def format_enum_as_assignment(enum_class: type[enum.Enum]) -> str:
    """Return one enum written as a name and the list of values it accepts

    Args:
        enum_class: The enum to write out

    Returns:
        The enum name followed by every value it accepts
    """
    return f"{enum_class.__name__} = {[member.value for member in enum_class]}"


def format_all_enums_as_assignments() -> str:
    """Return every enum a script can use written as a list of accepted values

    Returns:
        One line per enum under a heading
    """
    return "Enums:\n" + "\n".join(f" - {format_enum_as_assignment(enum_class)}" for enum_class in ALL_ENUMS)


def format_yaml_structure() -> str:
    """Return the skeleton of a script file with the two top level blocks

    Returns:
        The hosts and steps blocks with a comment on each
    """
    return YAML_STRUCTURE


def format_example_script() -> str:
    """Return the annotated example script shipped with the package

    Returns:
        The text of the example script file
    """
    return (files(EXAMPLE_SCRIPT_PACKAGE) / EXAMPLE_SCRIPT_FILENAME).read_text(encoding="utf-8")


def format_docs_overview() -> str:
    """Return the page printed when docs is asked for without any flags

    Returns:
        The script structure, the enums, the models that can be asked about and where to find an example
    """
    step_names = ", ".join(step_type.value for step_type in StepTypes)
    model_lines = "\n".join(
        [
            "Models:",
            f" - step types: {step_names}",
            f" - hosts block: {DocModelTypes.HOST.value}",
        ]
    )
    usage_rows = [
        ("tunnelrat docs --model <name>", "print the yaml keys of one model"),
        (f"tunnelrat docs --model {DocModelTypes.ALL.value}", "print the yaml keys of every model"),
        ("tunnelrat docs --example", "print a full example script"),
    ]
    invocation_width = max(len(invocation) for invocation, _ in usage_rows)
    usage_lines = "\n".join(
        ["Usage:", *(f" - {invocation.ljust(invocation_width)}   {summary}" for invocation, summary in usage_rows)]
    )
    return "\n\n".join([format_yaml_structure().rstrip(), format_all_enums_as_assignments(), model_lines, usage_lines])
