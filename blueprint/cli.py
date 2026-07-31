import argparse
import shutil
import sys
from importlib import resources
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

DEFAULT_SKILL_DIR = Path.home() / ".claude" / "skills" / "blueprint-synth"


def _package_version() -> str:
    try:
        return version("blueprint-synth")
    except PackageNotFoundError:
        return "unknown"


def _copy_tree(source, dest: Path) -> int:
    # source is an importlib Traversable, which is a real directory for a normal
    # wheel install but may be zip-backed, so walk it rather than assuming a path.
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for entry in source.iterdir():
        if entry.name == "__pycache__":
            continue
        if entry.is_dir():
            copied += _copy_tree(entry, dest / entry.name)
        elif entry.name.endswith(".md"):
            (dest / entry.name).write_text(entry.read_text(encoding="utf-8"), encoding="utf-8")
            copied += 1
    return copied


def install_skill(dest: Path, force: bool) -> int:
    if dest.exists():
        if not force:
            print(
                f"{dest} already exists. Re-run with --force to overwrite it.",
                file=sys.stderr,
            )
            return 1
        shutil.rmtree(dest)

    source = resources.files("blueprint.skill")
    count = _copy_tree(source, dest)

    if count == 0:
        print(
            "No skill files found in the installed package. This build may be "
            "missing its package data.",
            file=sys.stderr,
        )
        return 1

    print(f"Installed the blueprint-synth skill ({count} files) to {dest}")
    print("Start a new session to pick it up.")
    return 0


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(
        prog="blueprint-synth",
        description="Utilities for the blueprint-synth synthetic data library.",
    )
    parser.add_argument("--version", action="version", version=_package_version())
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser(
        "install-skill",
        help="Copy the bundled Agent Skill into your skills directory so a coding "
             "agent knows how to use this library.",
    )
    install.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_SKILL_DIR,
        help=f"Where to install the skill (default: {DEFAULT_SKILL_DIR})",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing installation.",
    )

    args = parser.parse_args(argv)

    if args.command == "install-skill":
        return install_skill(args.dest, args.force)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
