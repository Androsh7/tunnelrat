"""Defines help commands for models"""

# Standard libraries
import types
from importlib.resources import files
from typing import Any, Union, get_args, get_origin

# Third-party libraries
from pydantic import BaseModel
from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

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
SYNTAX_THEME = "ansi_dark"

SCRIPT_STRUCTURE_BODY = """steps:              # steps in order
  - <step type>:
      <step key>: <value>"""

USAGE_ROWS = [
    ("tunnelrat docs --model <name>", "print the yaml keys of one model"),
    ("tunnelrat docs --model all", "print the yaml keys of every model"),
    ("tunnelrat docs --example", "print a full example script"),
]


def format_type(annotation: Any) -> str:
    """Return a type annotation written the way a script author would read it

    Args:
        annotation: The annotation taken from a model field

    Returns:
        The name of the type, with unions joined by "or" and generics keeping their arguments
    """
    origin = get_origin(annotation)

    # Unions like Union[int, str] and int | str
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


def build_model_table(model: type[BaseModel], title: str) -> Table:
    """Return the yaml keys of one model drawn as a titled rich table

    Args:
        model: The model to describe
        title: The heading shown above the table

    Returns:
        A table of yaml key, type, default and description, with loader injected fields left out
    """
    table = Table(title=title, box=box.ROUNDED, title_style="bold cyan", header_style="bold", expand=False)
    table.add_column("key", style="green", no_wrap=True)
    table.add_column("type", style="yellow")
    table.add_column("default", style="magenta")
    table.add_column("description", max_width=MAX_DESCRIPTION_COLUMN_WIDTH)
    for field_name, field_info in model.model_fields.items():
        if is_loader_injected(field_info):
            continue
        yaml_key = field_info.alias or field_name
        default = "(required)" if field_info.is_required() else repr(field_info.default)
        table.add_row(yaml_key, format_type(field_info.annotation), default, field_info.description or "")
    return table


def build_all_model_tables() -> Group:
    """Return a table for every documented model stacked with a blank line between each

    Returns:
        A group holding one table per step model
    """
    renderables = []
    for step_type, model in STEP_TO_MODEL.items():
        renderables.append(build_model_table(model=model, title=step_type.value))
        renderables.append(Text())
    return Group(*renderables)


def build_enum_table() -> Table:
    """Return every enum a script can use drawn as a rich table

    Returns:
        A table of enum name and the values it accepts
    """
    table = Table(title="Enums", box=box.SIMPLE_HEAVY, title_style="bold cyan", header_style="bold", expand=False)
    table.add_column("enum", style="green", no_wrap=True)
    table.add_column("accepted values", style="yellow")
    for enum_class in ALL_ENUMS:
        table.add_row(enum_class.__name__, ", ".join(member.value for member in enum_class))
    return table


def build_usage_table() -> Table:
    """Return the docs command examples drawn as a rich table

    Returns:
        A table of example invocation and what it prints
    """
    table = Table(title="Usage", box=box.SIMPLE, title_style="bold cyan", show_header=False, expand=False)
    table.add_column(style="green", no_wrap=True)
    table.add_column()
    for invocation, summary in USAGE_ROWS:
        table.add_row(invocation, summary)
    return table


def build_example_script() -> Syntax:
    """Return the annotated example script shipped with the package as highlighted yaml

    Returns:
        The text of the example script file ready to print
    """
    text = (files(EXAMPLE_SCRIPT_PACKAGE) / EXAMPLE_SCRIPT_FILENAME).read_text(encoding="utf-8")
    return Syntax(text, "yaml", theme=SYNTAX_THEME, background_color="default")


def build_docs_overview() -> Group:
    """Return the page shown when docs is asked for without any flags

    Returns:
        The script structure, the enums, the step types and where to find an example
    """
    step_names = ", ".join(step_type.value for step_type in StepTypes)
    structure = Panel(
        Syntax(SCRIPT_STRUCTURE_BODY, "yaml", theme=SYNTAX_THEME, background_color="default"),
        title="Script structure",
        border_style="cyan",
        expand=False,
    )
    step_types_line = Text.assemble(("Step types: ", "bold"), (step_names, "yellow"))
    return Group(
        structure,
        Text(),
        build_enum_table(),
        Text(),
        step_types_line,
        Text(),
        build_usage_table(),
    )
