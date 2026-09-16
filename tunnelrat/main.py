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
    build_all_model_tables,
    build_docs_overview,
    build_enum_table,
    build_example_script,
    build_model_table,
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
        choices=[*StepTypes, "all"],
        help="Print documentation for a specific model, or 'all' for every model",
    )

    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    console = Console()

    if args.command == "docs":
        if args.example:
            console.print(build_example_script())
            sys.exit(0)
        if args.model is None:
            console.print(build_docs_overview())
            sys.exit(0)
        console.print(build_enum_table())
        if args.model == "all":
            console.print(build_all_model_tables())
        else:
            console.print(build_model_table(model=STEP_TO_MODEL[args.model], title=args.model))
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
