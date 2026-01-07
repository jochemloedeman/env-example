import argparse
from ast import (
    ClassDef,
)
from collections import defaultdict
from pathlib import Path

from env_example.ast_utils import (
    SettingField,
    extract_fields_from_settings,
    extract_settings_from_file,
)

DEFAULT_EXCLUDE_DIRS = {".venv"}


def build_env_example(setting_fields: list[SettingField]) -> str:
    example: str = ""
    fields_by_class: defaultdict[str, list] = defaultdict(list)
    for s in setting_fields:
        fields_by_class[s.settings_class].append(s)

    for settings_class in fields_by_class:
        example += f"# {settings_class}" + "\n"
        for field in fields_by_class[settings_class]:
            example += f"{field.prefix or ''}{field.name}=".upper() + "\n"
    return example


def run(
    dir: Path | None,
    exclude_dirs: list[str] | None,
) -> None:
    dir: Path = dir or Path.cwd()

    exclude: set[str] = DEFAULT_EXCLUDE_DIRS
    if exclude_dirs:
        exclude.update(set(exclude_dirs))

    settings_defs: list[ClassDef] = []
    for root, dirs, files in dir.walk(top_down=True):
        dirs[:] = [d for d in dirs if d not in exclude]
        py_files = [root / f for f in files if f.endswith(".py")]
        defs = [
            cd
            for file in py_files
            for cd in extract_settings_from_file(file.read_text())
        ]
        settings_defs.extend(defs)

    fields: list[SettingField] = [
        field
        for cd in settings_defs
        for field in extract_fields_from_settings(cd)
    ]

    env_example_txt = build_env_example(fields)

    target_file = dir / ".env.example"
    target_file.write_text(env_example_txt)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=None, type=Path)
    parser.add_argument(
        "--exclude-dir",
        default=None,
        type=str,
        action="append",
    )
    namespace = parser.parse_args()

    run(
        dir=namespace.project_root,
        exclude_dirs=namespace.exclude_dir,
    )


if __name__ == "__main__":
    main()
