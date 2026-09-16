"""Main entrypoint"""

# Standard libraries
import asyncio
import sys
from argparse import ArgumentParser
from pathlib import Path

# Third-party libraries
from rich.console import Console
from rich.live import Live

# Project libraries
from tunnelrat.constants import VERSION, StepTypes
from tunnelrat.docs.help import (
    format_all_enums_as_assignments,
    format_all_model_tables,
    format_docs_overview,
    format_example_script,
    model_to_specification_table,
)
from tunnelrat.exceptions import TunnelratBackendAbortError
from tunnelrat.script import STEP_TO_MODEL, Script
from tunnelrat.ssh.connection_manager import connection_manager
from tunnelrat.ui.script_ui import ScriptUI


async def main():
    """Main function"""
    parser = ArgumentParser(prog="tunnelrat", description="SSH Connection and Forward Manager")
    parser.add_argument("--version", action="version", version=f"tunnelrat v{VERSION}")
    command_arg_subparser = parser.add_subparsers(title="command", dest="command", required=True)

    script_parser = command_arg_subparser.add_parser(name="script", help="Commands for running yaml script")
    script_parser.add_argument("--file", "-f", type=Path, required=True, help="Path to the yaml script file to run")

    docs_parser = command_arg_subparser.add_parser(name="docs", help="Docs for writing scripts")
    docs_parser.add_argument("--example", action="store_true", help="Print a full example script")
    docs_parser.add_argument(
        "--model",
        default=None,
        choices=[StepTypes, "all"],
        help="Print documentation for a specific model, or 'all' for every model",
    )

    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    console = Console()

    if args.command == "docs":
        if args.example:
            sys.stdout.write(format_example_script() + "\n")
            sys.exit(0)
        if args.model is None:
            sys.stdout.write(format_docs_overview() + "\n")
            sys.exit(0)
        sys.stdout.write(format_all_enums_as_assignments() + "\n\n")
        if args.model == "all":
            sys.stdout.write(format_all_model_tables() + "\n")
        else:
            sys.stdout.write(model_to_specification_table(model=STEP_TO_MODEL[args.model], title=args.model) + "\n")
        sys.exit(0)

    elif args.command == "script":
        script = Script.from_yaml_path(args.file)
        with Live(ScriptUI(script), console=console, refresh_per_second=15, auto_refresh=True) as live:
            try:
                await script.run_script()
                live.refresh()
            except TunnelratBackendAbortError:
                pass
            except asyncio.CancelledError:
                asyncio.current_task().uncancel()
            finally:
                if len(connection_manager.connection_list) > 0:
                    await connection_manager.close_all()
                live.refresh()


if __name__ == "__main__":
    asyncio.run(main())
