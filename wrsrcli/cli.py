"""Command-line interface for wrsrcli.

Every subcommand from SPEC.md is defined with its documented arguments.
Commands that are not built yet report so and exit non-zero.
"""

import argparse
import textwrap
import sys

from . import __released__, __version__, WEBSITE, commands, install
from .errors import WrsrcliError

WIDTH = 80
RULE = "=" * WIDTH
# Command names are padded to this, so descriptions line up in one column.
NAME_COLUMN = 14


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


class _RootParser(_RustParser):
    """The top-level parser, which prints a banner instead of a usage line.

    `wrsrcli` with no arguments is someone asking what this is (D-017), so
    the answer leads with what it is and what it can do, not with argparse's
    grammar. Subcommand help is left exactly as argparse renders it — there
    the usage line is the useful part.
    """

    def format_help(self):
        rust = commands.enable_ansi()

        def accent(text):
            return commands.rust(text, rust)

        version = f"v{__version__} - {__released__}"
        website = f"See {WEBSITE} for more information"

        lines = [
            "",
            accent(RULE),
            accent("wrsrcli") + version.rjust(WIDTH - len("wrsrcli")),
            website.rjust(WIDTH),
            accent(RULE),
            "",
        ]

        intro = f"{self.description} wrsrcli supports the following commands:"
        lines += textwrap.wrap(intro, WIDTH)
        lines.append("")

        for name, help_text in _command_list(self):
            lines.append(f"    {accent(name.ljust(NAME_COLUMN))}{help_text}")
        lines.append("")

        lines.append(accent("options:"))
        for flags, help_text in _option_list(self):
            lines.append(f"  {accent(flags.ljust(NAME_COLUMN + 2))}{help_text}")
        lines.append("")

        lines += [
            "For more information about each command, append -h or --help. E.g.,",
            f"    {accent('wrsrcli scan -h')}     show more information about scan.",
            "",
            accent(RULE),
            "",
        ]
        return "\n".join(lines) + "\n"


def _command_list(parser):
    """(name, help) for every subcommand, in the order they were added."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return [
                (choice.dest, choice.help or "")
                for choice in action._choices_actions
            ]
    return []


def _option_list(parser):
    """(flags, help) for the top-level options."""
    found = []
    for action in parser._actions:
        if not action.option_strings:
            continue
        flags = ", ".join(action.option_strings)
        found.append((flags, (action.help or "").replace("%(prog)s", parser.prog)))
    return found


def _not_implemented(command):
    """Build a handler that reports `command` as unimplemented."""

    def handler(args):
        print(f"wrsrcli: '{command}' is not implemented yet.", file=sys.stderr)
        return 1

    return handler


class _RustRawEpilogFormatter(_RustHelpFormatter):
    """As `_RustHelpFormatter`, but leaves given line breaks alone.

    argparse fills the description and the epilog through the same hook, so
    keeping an example's layout means taking over both. `_describe` wraps
    the description itself before handing it over.
    """

    def _fill_text(self, text, width, indent):
        return "\n".join(indent + line for line in text.splitlines())


def _describe(parser, description, example=None):
    """Give a subparser its longer help, shown by `wrsrcli {command} -h`."""
    if example:
        # Wrapped here to the banner's width, because the formatter that
        # preserves the example's line breaks cannot also wrap this.
        parser.description = textwrap.fill(description, WIDTH - 2)
        parser.epilog = example
        parser.formatter_class = _RustRawEpilogFormatter
    else:
        parser.description = description
    return parser


def build_parser():
    parser = _RootParser(
        prog="wrsrcli",
        description=(
            "Inventory, document, and manage Steam Workshop assets for "
            "Workers & Resources: Soviet Republic."
        ),
    )
    parser.add_argument("--version", action="version", version=f"wrsrcli {__version__}")

    # Subcommands get the ordinary formatter, not the root's banner: there the
    # usage line and the argument list are the useful part.
    subcommands = parser.add_subparsers(
        dest="command", metavar="<command>", parser_class=_RustParser
    )
    subcommands.required = True

    scan = subcommands.add_parser(
        "scan", help="build manifest.json from the local workshop folder"
    )
    _describe(
        scan,
        "Read Steam's records and your workshop folder, and write an inventory "
        "of every installed item to manifest.json. Asks Steam for each item's "
        "title, author, published date, size and required items, and reports "
        "any dependency that is not installed. Steam must be running for that "
        "part; without it the inventory is still written from local files. "
        "Re-run this whenever you subscribe to or unsubscribe from anything.",
    )
    scan.set_defaults(func=commands.cmd_scan)

    output_table = subcommands.add_parser(
        "output-table", help="render a searchable HTML table from manifest.json"
    )
    _describe(
        output_table,
        "Turn the manifest into WRSR Assets.html: one self-contained file with "
        "search, a type filter, sortable columns, links to each item and its "
        "author, and a fold-down showing what each item depends on. Reads only "
        "the manifest, so it needs neither Steam nor an internet connection. "
        "Run scan first.",
    )
    output_table.set_defaults(func=commands.cmd_output_table)

    update = subcommands.add_parser(
        "update", help="subscribe to missing dependencies and updates"
    )
    _describe(
        update,
        "Subscribe to everything the inventory says is needed: items your mods "
        "require but that are not installed, and items with a newer version "
        "published. Lists what it will do and waits for ENTER first. Steam "
        "installs each item and keeps it updated from then on, exactly as if "
        "you had clicked Subscribe yourself. Needs Steam running.",
    )
    update.set_defaults(func=commands.cmd_update)

    import_ = subcommands.add_parser(
        "import", help="apply a YAML import list's copy/remove operations"
    )
    _describe(
        import_,
        "Apply an import list: a YAML file describing files to copy into the "
        "game or into another item's folder, and files to remove. Everything "
        "it overwrites or deletes is backed up first, so restore and rollback "
        "can undo it. Items the list needs are subscribed to through Steam.",
        "example:\n  wrsrcli import mylist.yaml",
    )
    import_.add_argument("path", help="path to the YAML import list")
    import_.set_defaults(func=commands.cmd_import)

    restore = subcommands.add_parser(
        "restore", help="restore files that imports overwrote on this item"
    )
    _describe(
        restore,
        "Put back the original files that an import overwrote inside this "
        "item's folder. Give the ID of the item whose files were changed. If "
        "more than one import touched it, you are asked which to restore.",
        "example:\n  wrsrcli restore 3621284903",
    )
    restore.add_argument("steamid", help="destination workshop item ID")
    restore.set_defaults(func=commands.cmd_restore)

    rollback = subcommands.add_parser(
        "rollback", help="undo changes this item's import made elsewhere"
    )
    _describe(
        rollback,
        "Undo everything an item's import list did: files it copied out are "
        "removed, and files it overwrote or deleted are put back. Give the ID "
        "of the item the import list was for, not the item it changed.",
        "example:\n  wrsrcli rollback 3780739284",
    )
    rollback.add_argument("steamid", help="origin workshop item ID")
    rollback.set_defaults(func=commands.cmd_rollback)

    manual_rerun = subcommands.add_parser(
        "manual-rerun", help="re-apply all tracked import lists"
    )
    _describe(
        manual_rerun,
        "Re-apply every import list you have run, from the copy wrsrcli kept "
        "at the time. Useful after Steam has updated an item and replaced "
        "files an import had changed. Anything overwritten is backed up again.",
    )
    manual_rerun.set_defaults(func=commands.cmd_manual_rerun)

    manual_check = subcommands.add_parser(
        "manual-check", help="flag tracked imports that Steam may have reverted"
    )
    _describe(
        manual_check,
        "Check whether anything an import changed has since been replaced — "
        "usually by Steam updating an item, or by verifying the game's files. "
        "Reports what looks reverted and changes nothing.",
    )
    manual_check.set_defaults(func=commands.cmd_manual_check)

    path = subcommands.add_parser("path", help="set or auto-detect game/workshop paths")
    _describe(
        path,
        "Show, set or detect where the game and your workshop items live. With "
        "no options it prints the current paths. Detection reads Steam's own "
        "registry entries and library files, so it copes with the game being "
        "on a second drive.",
        "examples:\n"
        "  wrsrcli path                    show the current paths\n"
        "  wrsrcli path --auto-detect      find them from Steam\n"
        '  wrsrcli path --game "D:\\Games\\SovietRepublic"',
    )
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
    _describe(
        install_,
        "Copy this executable somewhere permanent and add it to your PATH, so "
        "you can type wrsrcli from any folder. Only applies to the downloaded "
        ".exe; if you installed with pip, pip has already done this. Needs no "
        "administrator rights.",
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
    _describe(
        uninstall,
        "Undo install: delete the copied executable and take it off your PATH. "
        "Your settings, manifest and backups are left alone — they live in "
        "%APPDATA%\\wrsrcli and are yours to remove if you want them gone.",
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
    _describe(
        open_web,
        f"Open {WEBSITE} in your default browser, where the documentation and "
        "the import-list format are published. Prints the address first, so it "
        "is still useful if no browser opens.",
    )
    open_web.set_defaults(func=commands.cmd_open_web)

    completion = subcommands.add_parser(
        "completion", help="set up Tab completion in PowerShell"
    )
    _describe(
        completion,
        "Print a PowerShell script that completes wrsrcli's commands and "
        "options when you press Tab. With --install it is added to your "
        "PowerShell profile for you, after showing what will be written.",
        "examples:\n"
        "  wrsrcli completion --install    add it to your profile\n"
        "  wrsrcli completion              print it, to add it yourself",
    )
    completion.add_argument(
        "-i",
        "--install",
        action="store_true",
        help="append it to your PowerShell profile",
    )
    completion.set_defaults(func=commands.cmd_completion)

    return parser


def completion_script():
    """A PowerShell Tab-completion script for the current command set.

    The command and option names are baked in at generation time rather than
    looked up by running wrsrcli on every keystroke: Tab has to feel
    instant, and spawning a process to answer it would not. The cost is that
    the script is a snapshot — upgrading wrsrcli means running
    `wrsrcli completion --install` again, which the header says.
    """
    parser = build_parser()
    commands_list = ", ".join(f"'{name}'" for name, _ in _command_list(parser))

    per_command = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, subparser in action.choices.items():
            flags = ", ".join(
                f"'{flag}'"
                for sub_action in subparser._actions
                for flag in sub_action.option_strings
            )
            per_command.append(f"        '{name}' = @({flags})")
        break

    options = "\n".join(per_command)
    # Deliberately ASCII-only: this is redirected to a .ps1 as often as it is
    # read, and a frozen build writing to a cp1252 console turns anything else
    # into a replacement character.
    return f"""# wrsrcli Tab completion for PowerShell - generated by wrsrcli {__version__}.
# Re-run `wrsrcli completion --install` after upgrading wrsrcli.
Register-ArgumentCompleter -Native -CommandName wrsrcli -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)

    $commands = @({commands_list})
    $options = @{{
{options}
    }}

    $tokens = @($commandAst.CommandElements | ForEach-Object {{ $_.ToString() }})
    $command = $null
    foreach ($token in $tokens[1..($tokens.Count - 1)]) {{
        if ($commands -contains $token) {{ $command = $token; break }}
    }}

    if ($null -eq $command) {{
        $candidates = $commands + @('-h', '--help', '--version')
    }} else {{
        $candidates = $options[$command]
    }}

    $candidates |
        Where-Object {{ $_ -like "$wordToComplete*" }} |
        Sort-Object |
        ForEach-Object {{
            [System.Management.Automation.CompletionResult]::new(
                $_, $_, 'ParameterValue', $_)
        }}
}}
"""


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
