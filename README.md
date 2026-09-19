# tunnelrat

tunnelrat is a scripting tool for SSH (think ansible but simpler). It takes a yaml script with a list of commands (connect to host, create forward, run command, wait 15 seconds, etc) and then executes them sequentially. This tool is designed for simple automation scripts and cronjobs where the overhead of ansible or other tools would be too much.

## Installation

tunnelrat targets Python 3.11 or newer and uses [uv](https://github.com/astral-sh/uv) for its environment.

```bash
uv sync
```

Prebuilt standalone executables for Linux and Windows are attached to each [GitHub Release](https://github.com/Androsh7/tunnelrat/releases), and the package is published to PyPI.

## Usage

Run a script:

```bash
tunnelrat script --file script.yaml
```

Or, from a checkout without installing:

```bash
uv run python -m tunnelrat script --file script.yaml
```

Read the built-in documentation:

```bash
tunnelrat docs                 # overview of every step type
tunnelrat docs --example       # print a full annotated example script
tunnelrat docs --model connect # documentation for one step type
tunnelrat docs --model all     # documentation for every step type
```

## Script format

A script is made up of a list of steps

```yaml
steps:
  - connect:
      name: bastion
      host: 10.0.0.10
      port: 22
      os: linux
      user: deploy
      password: deploy_password
      sudo_password: deploy_password
      timeout: 30

  - connect:
      name: database:
      host: 10.0.1.25
      os: linux
      user: dbadmin
      ssh_key_path: ~/.ssh/id_ed25519
      ssh_key_password: key_passphrase

  - comment:
      body: Starting the nightly maintenance run

  - command:
      via: bastion
      script: uptime

  - command:
      via: bastion
      script: systemctl restart nginx
      sudo: true

  - batch:
      via: [bastion, database]
      script: df -h /
      output_dir: ./output/disk_usage
      stdout_output: true

  - forward:
      type: local
      via: bastion
      local_host: 127.0.0.1
      local_port: 15432
      remote_host: 10.0.1.25
      remote_port: 5432

  - wait:
      time: 5

  - block:
      timeout: 3600
```

`tunnelrat docs --example` prints a fuller version of this covering every option.

### Step types

| Step      | Purpose                                                                          |
| --------- | -------------------------------------------------------------------------------- |
| `connect` | Open an SSH connection to a host.                                                |
| `forward` | Open a `local` or `remote` port forward through a named host.                    |
| `command` | Run one script on one host, optionally under sudo, with optional output capture. |
| `batch`   | Run one script across several hosts in a single step.                            |
| `wait`    | Pause for a fixed number of seconds.                                             |
| `block`   | Hold the script open (keeping tunnels up) until interrupted, or until a timeout. |
| `comment` | Print a message in the dashboard.                                                |

Each host declares its `os` (`linux` or `windows`), which decides how commands are built and encoded for that target. Commands can select an interpreter with `executable`; the supported values are `bash`, `sh`, `pwsh`, and `python` on Linux, and `powershell`, `cmd`, and `python` on Windows.

## Development

The project follows a strict lint and format baseline enforced by Ruff.

```bash
uv sync
uv run ruff check --fix . && uv run ruff format .
uv run pytest
```

A `docker-compose.yml` under `tests/` starts a local OpenSSH server for exercising real connections.

### Building executables

`compile_script.py` compiles tunnelrat into a distributable binary with [Nuitka](https://nuitka.net/):

```bash
uv run --extra dev python compile_script.py
```

The `.github/workflows/` pipelines build Linux onefile binaries (glibc and musl, x86_64 and arm64) and Windows standalone installers on every push to `main`, tag releases from `VERSION.txt` and `CHANGELOG.md`, and publish to PyPI.
