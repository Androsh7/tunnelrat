"""Compile tunnelrat into a distributable executable with Nuitka"""

# Standard libraries
import platform
import subprocess
import sys
from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from enum import StrEnum
from pathlib import Path

# Third-party libraries
from attrs import define, field, validators
from loguru import logger

REPOSITORY_ROOT = Path(__file__).parent
ENTRY_POINT = REPOSITORY_ROOT / "tunnelrat" / "main.py"
VERSION_FILE = REPOSITORY_ROOT / "VERSION.txt"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "dist"
PROJECT_NAME = "tunnelrat"
WINDOWS_EXECUTABLE_SUFFIX = ".exe"

# Data the compiled package reads at runtime, mapped as source=destination inside the payload
INCLUDED_DATA_FILES = (
    "VERSION.txt=VERSION.txt",
    "tunnelrat/docs/example_script.yaml=docs/example_script.yaml",
)

GLIBC_LIBRARY_NAME = "glibc"

# The folder and executable Nuitka produces for a standalone build of the entry point
STANDALONE_DISTRIBUTION_SUFFIX = ".dist"
STANDALONE_EXECUTABLE_NAME = f"{PROJECT_NAME}{WINDOWS_EXECUTABLE_SUFFIX}"

# Inno Setup command-line compiler and the identifiers it uses to describe target architectures
INSTALLER_COMPILER = "iscc"
INSTALLER_SCRIPT_SUFFIX = ".iss"
INSTALLER_SETUP_SUFFIX = "-setup"


class OperatingSystem(StrEnum):
    """Enumerate the operating systems an executable can target"""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"


class Architecture(StrEnum):
    """Enumerate the processor architectures an executable can target"""

    X86_64 = "x86_64"
    ARM64 = "arm64"


class LibraryC(StrEnum):
    """Enumerate the C standard libraries a Linux executable can link against"""

    GLIBC = "glibc"
    MUSL = "musl"
    NONE = "none"


class BuildMode(StrEnum):
    """Enumerate the ways Nuitka can package the executable"""

    ONEFILE = "onefile"
    STANDALONE = "standalone"


INNO_SETUP_ARCHITECTURE = {
    Architecture.X86_64: "x64compatible",
    Architecture.ARM64: "arm64",
}


def read_version() -> str:
    """Return the project version recorded in the version file"""
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def detect_operating_system() -> OperatingSystem:
    """Return the operating system the build is currently running on

    Raises:
        ValueError: If the current operating system is not one this script targets
    """
    system_name = platform.system().lower()
    if system_name == "linux":
        return OperatingSystem.LINUX
    if system_name == "windows":
        return OperatingSystem.WINDOWS
    if system_name == "darwin":
        return OperatingSystem.MACOS
    raise ValueError(f"Unsupported operating system: {system_name}")


def detect_architecture() -> Architecture:
    """Return the processor architecture the build is currently running on

    Raises:
        ValueError: If the current architecture is not one this script targets
    """
    machine_name = platform.machine().lower()
    if machine_name in {"x86_64", "amd64"}:
        return Architecture.X86_64
    if machine_name in {"arm64", "aarch64"}:
        return Architecture.ARM64
    raise ValueError(f"Unsupported architecture: {machine_name}")


def detect_library_c(operating_system: OperatingSystem) -> LibraryC:
    """Return the C standard library the build is currently running against

    Args:
        operating_system: The operating system the build targets

    Returns:
        The detected C library on Linux, or the sentinel for platforms where it does not apply
    """
    if operating_system is not OperatingSystem.LINUX:
        return LibraryC.NONE
    detected_library_name = platform.libc_ver()[0].lower()
    if detected_library_name.startswith(GLIBC_LIBRARY_NAME):
        return LibraryC.GLIBC
    return LibraryC.MUSL


def default_build_mode(operating_system: OperatingSystem) -> BuildMode:
    """Return the packaging mode that suits an operating system

    Args:
        operating_system: The operating system the build targets

    Returns:
        A standalone build on Windows so it can be wrapped in an installer, a onefile build elsewhere
    """
    if operating_system is OperatingSystem.WINDOWS:
        return BuildMode.STANDALONE
    return BuildMode.ONEFILE


@define
class BuildConfiguration:
    """Hold the resolved settings for one executable build"""

    operating_system: OperatingSystem = field(validator=validators.instance_of(OperatingSystem))
    architecture: Architecture = field(validator=validators.instance_of(Architecture))
    library_c: LibraryC = field(validator=validators.instance_of(LibraryC))
    build_mode: BuildMode = field(validator=validators.instance_of(BuildMode))
    output_directory: Path = field(validator=validators.instance_of(Path))
    build_installer: bool = field(validator=validators.instance_of(bool))
    assume_yes_for_downloads: bool = field(validator=validators.instance_of(bool))

    @property
    def target_label(self) -> str:
        """Return the operating-system, architecture and library triple naming this target"""
        label_parts = [self.operating_system.value, self.architecture.value]
        if self.library_c is not LibraryC.NONE:
            label_parts.append(self.library_c.value)
        return "-".join(label_parts)

    @property
    def artifact_stem(self) -> str:
        """Return the base name shared by every file this build produces"""
        return f"{PROJECT_NAME}-{read_version()}-{self.target_label}"

    @property
    def onefile_name(self) -> str:
        """Return the filename of the single-file executable a onefile build produces"""
        if self.operating_system is OperatingSystem.WINDOWS:
            return f"{self.artifact_stem}{WINDOWS_EXECUTABLE_SUFFIX}"
        return self.artifact_stem

    @property
    def distribution_directory(self) -> Path:
        """Return the folder Nuitka fills with the standalone build"""
        return self.output_directory / f"{ENTRY_POINT.stem}{STANDALONE_DISTRIBUTION_SUFFIX}"

    @property
    def installer_script_path(self) -> Path:
        """Return the path of the generated Inno Setup script"""
        return self.output_directory / f"{self.artifact_stem}{INSTALLER_SCRIPT_SUFFIX}"

    @property
    def installer_base_name(self) -> str:
        """Return the filename stem of the compiled installer, without a suffix"""
        return f"{self.artifact_stem}{INSTALLER_SETUP_SUFFIX}"

    def nuitka_command(self) -> list[str]:
        """Return the Nuitka command line that compiles the entry point"""
        command = [
            sys.executable,
            "-m",
            "nuitka",
            "--standalone",
            "--remove-output",
            f"--include-distribution-metadata={PROJECT_NAME}",
            f"--output-dir={self.output_directory}",
        ]
        if self.build_mode is BuildMode.ONEFILE:
            command.append("--onefile")
            command.append(f"--output-filename={self.onefile_name}")
        else:
            command.append(f"--output-filename={STANDALONE_EXECUTABLE_NAME}")
        if self.operating_system is OperatingSystem.WINDOWS:
            command.append(f"--windows-product-name={PROJECT_NAME}")
            command.append(f"--windows-product-version={read_version()}")
            command.append(f"--windows-file-version={read_version()}")
        if self.assume_yes_for_downloads:
            command.append("--assume-yes-for-downloads")
        command.extend(f"--include-data-file={data_file}" for data_file in INCLUDED_DATA_FILES)
        command.append(str(ENTRY_POINT))
        return command


def build_installer_script(configuration: BuildConfiguration) -> str:
    """Return the Inno Setup script that packages a standalone build into an installer

    Args:
        configuration: The settings describing the standalone build to wrap

    Returns:
        The full text of an Inno Setup script
    """
    architecture_identifier = INNO_SETUP_ARCHITECTURE[configuration.architecture]
    return "\n".join(
        [
            "[Setup]",
            f"AppName={PROJECT_NAME}",
            f"AppVersion={read_version()}",
            f"DefaultDirName={{autopf}}\\{PROJECT_NAME}",
            f"DefaultGroupName={PROJECT_NAME}",
            f"OutputDir={configuration.output_directory}",
            f"OutputBaseFilename={configuration.installer_base_name}",
            f"ArchitecturesAllowed={architecture_identifier}",
            f"ArchitecturesInstallIn64BitMode={architecture_identifier}",
            "Compression=lzma2",
            "SolidCompression=yes",
            "",
            "[Files]",
            f'Source: "{configuration.distribution_directory}\\*"; DestDir: "{{app}}"; '
            "Flags: recursesubdirs createallsubdirs",
            "",
            "[Icons]",
            f'Name: "{{group}}\\{PROJECT_NAME}"; Filename: "{{app}}\\{STANDALONE_EXECUTABLE_NAME}"',
            "",
        ]
    )


def compile_installer(configuration: BuildConfiguration) -> Path:
    """Write the Inno Setup script for a standalone build and compile it into an installer

    Args:
        configuration: The settings describing the standalone build to wrap

    Raises:
        CalledProcessError: If the Inno Setup compiler exits with a non-zero status
        FileNotFoundError: If the compiler is missing or produces no installer

    Returns:
        The path of the compiled installer executable
    """
    configuration.installer_script_path.write_text(build_installer_script(configuration), encoding="utf-8")
    logger.info("Wrote installer script to {}", configuration.installer_script_path)
    subprocess.run([INSTALLER_COMPILER, str(configuration.installer_script_path)], check=True)
    installer_path = configuration.output_directory / f"{configuration.installer_base_name}{WINDOWS_EXECUTABLE_SUFFIX}"
    if not installer_path.is_file():
        raise FileNotFoundError(f"Inno Setup reported success but {installer_path} is missing")
    logger.info("Wrote installer to {}", installer_path)
    return installer_path


def run_nuitka(configuration: BuildConfiguration) -> Path:
    """Compile the entry point with Nuitka and return the path it produced

    Args:
        configuration: The settings describing the build

    Raises:
        CalledProcessError: If Nuitka exits with a non-zero status
        FileNotFoundError: If Nuitka reports success but its output is missing

    Returns:
        The single-file executable for a onefile build, or the distribution folder for a standalone build
    """
    configuration.output_directory.mkdir(parents=True, exist_ok=True)
    command = configuration.nuitka_command()
    logger.info("Compiling {} with: {}", configuration.artifact_stem, " ".join(command))
    subprocess.run(command, check=True)
    produced_path = (
        configuration.output_directory / configuration.onefile_name
        if configuration.build_mode is BuildMode.ONEFILE
        else configuration.distribution_directory
    )
    if not produced_path.exists():
        raise FileNotFoundError(f"Nuitka reported success but {produced_path} is missing")
    logger.info("Nuitka produced {}", produced_path)
    return produced_path


def run_build(configuration: BuildConfiguration) -> Path:
    """Run the full build described by a configuration and return the artifact to publish

    Args:
        configuration: The settings describing the build

    Returns:
        The installer for a standalone Windows build, otherwise the compiled executable or folder
    """
    produced_path = run_nuitka(configuration)
    if configuration.build_mode is BuildMode.STANDALONE and configuration.build_installer:
        return compile_installer(configuration)
    return produced_path


def parse_arguments() -> Namespace:
    """Return the parsed command-line arguments, defaulting to the detected build platform"""
    detected_operating_system = detect_operating_system()
    parser = ArgumentParser(prog="build_executable", description="Compile tunnelrat into a distributable executable")
    parser.add_argument(
        "--operating-system",
        type=OperatingSystem,
        choices=list(OperatingSystem),
        default=detected_operating_system,
        help="Operating system the executable is labelled for",
    )
    parser.add_argument(
        "--architecture",
        type=Architecture,
        choices=list(Architecture),
        default=detect_architecture(),
        help="Processor architecture the executable is labelled for",
    )
    parser.add_argument(
        "--library-c",
        type=LibraryC,
        choices=list(LibraryC),
        default=detect_library_c(detected_operating_system),
        help="C standard library the Linux executable links against",
    )
    parser.add_argument(
        "--build-mode",
        type=BuildMode,
        choices=list(BuildMode),
        default=default_build_mode(detected_operating_system),
        help="Whether Nuitka packages a single file or a standalone folder",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory the build writes its output to",
    )
    parser.add_argument(
        "--installer",
        action=BooleanOptionalAction,
        default=True,
        help="Compile an installer from a standalone build with Inno Setup",
    )
    parser.add_argument(
        "--assume-yes-for-downloads",
        action=BooleanOptionalAction,
        default=True,
        help="Let Nuitka download the components it needs without prompting",
    )
    return parser.parse_args()


def build_configuration_from_arguments(arguments: Namespace) -> BuildConfiguration:
    """Return a build configuration assembled from parsed command-line arguments

    Args:
        arguments: The namespace produced by the argument parser

    Returns:
        The configuration describing the build to run
    """
    return BuildConfiguration(
        operating_system=arguments.operating_system,
        architecture=arguments.architecture,
        library_c=arguments.library_c,
        build_mode=arguments.build_mode,
        output_directory=arguments.output_directory,
        build_installer=arguments.installer,
        assume_yes_for_downloads=arguments.assume_yes_for_downloads,
    )


def main() -> int:
    """Run the build described by the command-line arguments and return an exit code"""
    configuration = build_configuration_from_arguments(parse_arguments())
    run_build(configuration)
    return 0


if __name__ == "__main__":
    sys.exit(main())
