"""Commands for the running app, written into its folder from the PC.

`./deploy.sh run <command>` writes each command as its own file `cmd/<ns>.cmd`: first
under a temporary name, then renamed, so a `.cmd` file is always complete. The names
are nanosecond timestamps, so name order is the order they were sent.
"""

from pathlib import Path

CMD_DIR = Path("/app/cmd")


def take_commands(cmd_dir: Path = CMD_DIR) -> list[str]:
    """Return the pending commands, oldest first, and delete their files."""
    if not cmd_dir.is_dir():
        return []
    commands = []
    for path in sorted(cmd_dir.glob("*.cmd")):
        text = path.read_text(encoding="utf-8").strip()
        path.unlink()
        if text:
            commands.append(text)
    return commands
