"""Main entrypoint"""

# Standard libraries
import asyncio
from argparse import ArgumentParser
from pathlib import Path

# Third-party libraries
from loguru import logger

# Project libraries
from tunnelrat.constants import VERSION
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

    args = parser.parse_args()

    try:
        if args.command == "script":
            script = Script.from_yaml_path(Path("./script.yaml"))
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
