"""Command-line interface for wrsrcli.

Every subcommand from SPEC.md is defined with its documented arguments.
Commands that are not built yet report so and exit non-zero.
"""

import argparse
import sys

from . import __version__, commands, install
from .errors import WrsrcliError


class _RustHelpFormatter(argparse.HelpFormatter):
    """Help with D-016's rusty red on the headings and the command names.

    Colour is applied *after* `argparse` has laid the text out, never before.
    The escape sequences are invisible on screen but not to `len()`, and the
    help column is positioned by measuring the command names — colouring them
    first pushes every description onto a line of its own.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rust = commands.enable_ansi()

    def _set_color(self, color):
        # Python 3.14+ colours the help itself, through this hook. This screen
        # brings its own accent, so argparse's palette is turned off rather
        # than layered underneath it.
        super()._set_color(False)

    def start_section(self, heading):
        super().start_section(
            commands.rust(heading, self._rust) if heading else heading
        )

    def _format_action(self, action):
        text = super()._format_action(action)
        if not self._rust:
            return text
        # The invocation is what `super()` has already padded the column to,
        # and it always precedes the description, so the first occurrence is
        # the one to paint.
        name = self._format_action_invocation(action)
        return text.replace(name, commands.rust(name, True), 1)

    def format_help(self):
        text = super().format_help()
        if not self._rust:
            return text
        if text.startswith("usage:"):
            text = commands.rust("usage:", True) + text[len("usage:") :]
        # A section's colon is appended outside the heading argparse was given,
        # so it lands after the reset. Move it back inside.
        return text.replace(f"{commands.RESET}:", f":{commands.RESET}")


class _RustParser(argparse.ArgumentParser):
    """An `ArgumentParser` whose help carries the accent unless told otherwise.

    Subparsers are built from `type(self)`, so every `wrsrcli {command} --help`
    inherits this without each one having to ask for it.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", _RustHelpFormatter)
        super().__init__(*args, **kwargs)


def _not_implemented(command):
    """Build a handler that reports `command` as unimplemented."""

    def handler(args):
        print(f"wrsrcli: '{command}' is not implemented yet.", file=sys.stderr)
        return 1

    return handler


def build_parser():
    parser = _RustParser(
        prog="wrsrcli",
        description=(
            "Inventory, document, and manage Steam Workshop assets for "
            "Workers & Resources: Soviet Republic."
        ),
    )
    parser.add_argument("--version", action="version", version=f"wrsrcli {__version__}")

    subcommands = parser.add_subparsers(dest="command", metavar="<command>")
    subcommands.required = True

    scan = subcommands.add_parser(
        "scan", help="build manifest.json from the local workshop folder"
    )
    scan.set_defaults(func=commands.cmd_scan)

    output_table = subcommands.add_parser(
        "output-table", help="render a searchable HTML table from manifest.json"
    )
    output_table.set_defaults(func=commands.cmd_output_table)

    import_ = subcommands.add_parser(
        "import", help="apply a YAML import list's copy/remove operations"
    )
    import_.add_argument("path", help="path to the YAML import list")
    import_.set_defaults(func=commands.cmd_import)

    restore = subcommands.add_parser(
        "restore", help="restore files that imports overwrote on this item"
    )
    restore.add_argument("steamid", help="destination workshop item ID")
    restore.set_defaults(func=commands.cmd_restore)

    rollback = subcommands.add_parser(
        "rollback", help="undo changes this item's import made elsewhere"
    )
    rollback.add_argument("steamid", help="origin workshop item ID")
    rollback.set_defaults(func=commands.cmd_rollback)

    manual_rerun = subcommands.add_parser(
        "manual-rerun", help="re-apply all tracked import lists"
    )
    manual_rerun.set_defaults(func=commands.cmd_manual_rerun)

    manual_check = subcommands.add_parser(
        "manual-check", help="flag tracked imports that Steam may have reverted"
    )
    manual_check.set_defaults(func=commands.cmd_manual_check)

    api = subcommands.add_parser("api", help="set or remove the Steam Web API key")
    api.add_argument("key", nargs="?", help="the Steam Web API key to store")
    api.add_argument(
        "-r", "--remove", action="store_true", help="remove the stored API key"
    )
    api.set_defaults(func=commands.cmd_api)

    path = subcommands.add_parser("path", help="set or auto-detect game/workshop paths")
    path.add_argument("-g", "--game", metavar="PATH", help="set the game install path")
    path.add_argument(
        "-w", "--workshop", metavar="PATH", help="set the workshop content path"
    )
    path.add_argument(
        "-a",
        "--auto-detect",
        action="store_true",
        help="detect both paths from the Windows registry",
    )
    path.set_defaults(func=commands.cmd_path)

    install_ = subcommands.add_parser(
        "install", help="put this executable on your PATH (standalone .exe only)"
    )
    install_.add_argument(
        "-p",
        "--path",
        metavar="PATH",
        help=r"install to PATH instead of %%LOCALAPPDATA%%\Programs\wrsrcli",
    )
    install_.set_defaults(func=commands.cmd_install)

    uninstall = subcommands.add_parser(
        "uninstall", help="remove the installed executable and its PATH entry"
    )
    uninstall.add_argument(
        "-p",
        "--path",
        metavar="PATH",
        help="uninstall from PATH instead of the default location",
    )
    uninstall.set_defaults(func=commands.cmd_uninstall)

    open_web = subcommands.add_parser(
        "open-web", help="open the wrsrcli website in your browser"
    )
    open_web.set_defaults(func=commands.cmd_open_web)

    steamcmd = subcommands.add_parser("steamcmd", help="install SteamCMD")
    steamcmd.add_argument(
        "-i", "--install", action="store_true", help="download and install SteamCMD"
    )
    steamcmd.add_argument(
        "-p",
        "--path",
        metavar="PATH",
        help="install to PATH instead of [STEAMPATH]/steamcmd",
    )
    steamcmd.set_defaults(func=commands.cmd_steamcmd)

    return parser


def main(argv=None):
    supplied = sys.argv[1:] if argv is None else argv

    # Double-clicked in Explorer with no arguments: argparse would print a
    # usage error into a window that closes before it can be read. Offer to
    # install instead, which is what someone who just downloaded this wants.
    if not supplied and install.is_frozen() and install.launched_from_explorer():
        return commands.first_run()

    parser = build_parser()

    # Bare `wrsrcli` shows the help rather than argparse's usage error. Someone
    # who types the name alone is asking what it does, and a two-line error is
    # a poor answer to that (decision D-017).
    if not supplied:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except WrsrcliError as exc:
        print(f"wrsrcli: {exc}", file=sys.stderr)
        if install.is_frozen() and install.launched_from_explorer():
            # Same problem: don't let the error vanish with the window.
            try:
                input("\nPress ENTER to close this window...")
            except EOFError:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
