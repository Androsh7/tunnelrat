"""Defines the ScriptUI class"""

# Third-party libraries
from attrs import define, field, validators
from rich.console import Console, Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

# Project libraries
from tunnelrat.constants import VERSION, StepTypes
from tunnelrat.script import Script, Step
from tunnelrat.ssh.connection_manager import connection_manager

console = Console()


def steps_panel(step_list: list[Step]):
    """Returns the step panel based on the steps in the script"""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(justify="right")  # step
    grid.add_column(justify="left")  # progress
    grid.add_column(justify="left")  # command details
    grid.add_column(justify="left")  # status
    for step in step_list:
        # get progress icon
        if step.step_type == StepTypes.COMMENT:
            progress = Text(" ")
        elif step.completed:
            progress = Text("▣", style="green")
        elif step.failed:
            progress = Text("✘", style="red")
        elif step.started:
            progress = Spinner("dots", style="yellow")
        else:
            progress = Text("☐", style="dim")

        grid.add_row(
            Text(str(step.step_number), style="dim"),
            progress,
            Text(str(step.config), style="bold"),
            Text(step.progress, style="yellow"),
        )

    completed_count = sum(1 for step in step_list if step.completed)
    header = Text.assemble(("Steps", "bold"), (f" - {completed_count}/{len(step_list)}", "dim"))
    return Group(header, grid)


def hosts_panel() -> Table:
    """Returns the host panel based on the connections and forwards"""
    grid = Table.grid(pad_edge=(0, 1), expand=True)
    grid.title = " --- Active connections --- "
    grid.title_style = "bold"
    grid.title_justify = "left"
    grid.add_column(justify="left")
    for connection in connection_manager.connection_list:
        grid.add_row(Text(str(connection)))
        for forward in connection.get_forward_list():
            grid.add_row(Text(f" - {forward}"))
    return grid


@define
class ScriptUI:
    """Render the live panel that shows a script running"""

    script: Script = field(validator=validators.instance_of(Script))

    def render(self) -> Panel:
        """Returns the full script runner UI"""
        columns = Table.grid(expand=True, padding=(0, 2))
        columns.add_column(ratio=2)
        columns.add_column(ratio=1)
        columns.add_row(steps_panel(self.script.step_list), hosts_panel())
        return Panel(
            columns,
            title=f"tunnelrat v{VERSION} - {self.script.script_path.name}",
            subtitle=self.script.script_path.resolve().as_posix(),
            expand=True,
        )

    def __rich__(self) -> Panel:
        """Method for triggering auto-refresh rendering"""
        return self.render()
