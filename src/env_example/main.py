import argparse
from collections import defaultdict
from pathlib import Path

from env_example.ast_utils import (
    ClassContext,
    SettingField,
    extract_class_contexts,
    extract_fields_from_settings,
    extract_settings_from_defs,
)

ALWAYS_EXCLUDE_DIRS = {".venv"}


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


def run(
    project_root: Path,
    exclude_relative: list[Path] | None,
) -> None:
    exclude_absolute = (
        {p.resolve() for p in exclude_relative} if exclude_relative else {}
    )

    contexts: list[ClassContext] = []
    for root, dirs, files in project_root.walk(top_down=True):
        dirs[:] = [
            d
            for d in dirs
            if d not in ALWAYS_EXCLUDE_DIRS
            and root / d not in exclude_absolute
        ]
        py_files = [root / f for f in files if f.endswith(".py")]
        dir_contexts = [
            cd
            for file in py_files
            for cd in extract_class_contexts(file.read_text())
        ]
        contexts.extend(dir_contexts)

    settings = extract_settings_from_defs(contexts=contexts)
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
