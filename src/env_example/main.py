import argparse
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from env_example.ast_utils import (
    ClassContext,
    SettingField,
    extract_class_contexts,
    extract_fields_from_settings,
    extract_settings,
)

ALWAYS_EXCLUDE_DIRS = {".venv", "site-packages"}


def build_env_example(setting_fields: list[SettingField]) -> str:
    example: str = ""
    fields_by_class: defaultdict[str, list] = defaultdict(list)
    for s in setting_fields:
        fields_by_class[s.settings_class].append(s)

    for settings_class in fields_by_class:
        example += f"# {settings_class}" + "\n"
        for field in fields_by_class[settings_class]:
            example += f"{field.prefix or ''}{field.name}=".upper() + "\n"
        example += "\n"

    example = example.removesuffix("\n")
    return example


def walk_project(
    root: Path,
    exclude_paths: set[Path],
) -> Iterator[ClassContext]:
    def walk_dir(dir: Path, parent_package: str) -> Iterator[ClassContext]:
        is_package = False
        for p in dir.iterdir():
            if p.name == "__init__.py":
                is_package = True
                break

        new_parent = (
            (f"{parent_package}.{dir.name}" if parent_package else dir.name)
            if is_package
            else ""
        )

        for item in dir.iterdir():
            if item.is_file() and item.suffix == ".py":
                yield from extract_class_contexts(
                    item.read_text(),
                    package=new_parent,
                )
            if (
                item.is_dir()
                and item.name not in ALWAYS_EXCLUDE_DIRS
                and item not in exclude_paths
            ):
                yield from walk_dir(item, parent_package=parent_package)

    yield from walk_dir(root, parent_package="")


def run(
    project_root: Path,
    exclude_relative: list[Path] | None,
) -> None:
    exclude_absolute: set[Path] = (
        {p.resolve() for p in exclude_relative} if exclude_relative else set()
    )

    contexts: list[ClassContext] = [
        context
        for context in walk_project(
            project_root,
            exclude_paths=exclude_absolute,
        )
    ]

    settings = extract_settings(contexts=contexts)
    fields: list[SettingField] = [
        field for cd in settings for field in extract_fields_from_settings(cd)
    ]

    env_example_txt = build_env_example(fields)
    target_file = project_root / ".env.example"
    target_file.write_text(env_example_txt)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exclude-dir",
        default=None,
        type=Path,
        action="append",
    )
    namespace = parser.parse_args()

    cwd = Path.cwd()
    run(
        project_root=cwd,
        exclude_relative=namespace.exclude_dir,
    )


if __name__ == "__main__":
    main()
