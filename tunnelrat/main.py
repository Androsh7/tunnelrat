"""Main entrypoint"""

# Standard libraries
import asyncio
import sys
from argparse import ArgumentParser
from pathlib import Path

# Third-party libraries
from loguru import logger

# Project libraries
from tunnelrat.constants import VERSION, DocModelTypes, StepTypes
from tunnelrat.docs.help import (
    DOCUMENTED_MODELS,
    format_all_enums_as_assignments,
    format_all_model_tables,
    format_docs_overview,
    format_example_script,
    model_to_specification_table,
)
from tunnelrat.script import Script
from tunnelrat.ssh.connection_manager import connection_manager


async def main():
    parser = ArgumentParser(prog="tunnelrat", description="SSH Connection and Forward Manager")
    parser.add_argument("--version", action="version", version=f"tunnelrat v{VERSION}")
    command_arg_subparser = parser.add_subparsers(title="command", dest="command", required=True)

    script_parser = command_arg_subparser.add_parser(name="script", help="Commands for running yaml script")
    script_parser.add_argument("--file", "-f", type=Path, required=True, help="Path to the yaml script file to run")
    script_parser.add_argument(
        "--dry-run", action="store_true", help="Goes through the script execution without running commands"
    )

    docs_parser = command_arg_subparser.add_parser(name="docs", help="Docs for writing scripts")
    docs_parser.add_argument("--example", action="store_true", help="Print a full example script")
    docs_parser.add_argument(
        "--model",
        default=None,
        choices=[*list(StepTypes), *list(DocModelTypes)],
        help="Print documentation for a specific model, or 'all' for every model",
    )

    args = parser.parse_args()

    try:
        if args.command == "docs":
            if args.example:
                print(format_example_script())
                sys.exit(0)
            if args.model is None:
                print(format_docs_overview())
                sys.exit(0)
            print(format_all_enums_as_assignments() + "\n")
            if args.model == DocModelTypes.ALL:
                print(format_all_model_tables())
            else:
                print(model_to_specification_table(model=DOCUMENTED_MODELS[args.model], title=args.model))
            sys.exit(0)

        elif args.command == "script":
            script = Script.from_yaml_path(args.file)
            await script.run_script(dry_run=args.dry_run)
    except asyncio.CancelledError:
        logger.warning("User executed interrupted")
        asyncio.current_task().uncancel()
    finally:
        if len(connection_manager.connection_list) > 0:
            logger.warning("Not all connections were cleaned up, closing remaining connections")
            await asyncio.run(connection_manager.close_all())


if __name__ == "__main__":
    asyncio.run(main())
