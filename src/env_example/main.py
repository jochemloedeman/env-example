import argparse
import ast
from collections import defaultdict
from pathlib import Path
from typing import Iterator

from env_example.ast_utils import (
    SettingField,
    extract_fields_from_settings,
    filter_module_by_type,
    get_bases_from_class,
    resolve_import_statements,
)

ALWAYS_EXCLUDE_DIRS = {".venv", "site-packages"}
BASE_SETTINGS_FQN = "pydantic_settings.BaseSettings"


class InheritanceHierarchy:
    def __init__(self) -> None:
        self._children: defaultdict[str, set] = defaultdict(set)

    def add_relation(self, parent: str, child: str):
        self._children[parent].add(child)

    def transitive_subclasses(self, class_name: str) -> set[str]:
        reachable = set()
        for child in self._children[class_name]:
            reachable.add(child)
            reachable.update(self.transitive_subclasses(child))
        return reachable


def build_env_example(fields_per_class: dict[str, list[SettingField]]) -> str:
    example: str = ""
    for class_name, fields in fields_per_class.items():
        example += f"# {class_name}" + "\n"
        for field in fields:
            example += f"{field.prefix or ''}{field.name}=".upper() + "\n"
        example += "\n"

    example = example.removesuffix("\n")
    return example


def walk_project(
    root: Path,
    exclude_paths: set[Path],
) -> Iterator[tuple[str, ast.Module]]:
    def walk_dir(
        dir: Path, parent_package: str
    ) -> Iterator[tuple[str, ast.Module]]:
        is_package = False
        for p in dir.iterdir():
            if p.name == "__init__.py":
                is_package = True
                break

        new_parent = (
            ".".join(filter(None, [parent_package, dir.name]))
            if is_package
            else ""
        )

        for item in sorted(dir.iterdir()):
            if is_package and item.is_file() and item.suffix == ".py":
                module = ast.parse(item.read_text())
                module_name = (
                    stem if (stem := item.stem) != "__init__" else None
                )
                module_fqn = ".".join(filter(None, [new_parent, module_name]))
                yield (module_fqn, module)

            if (
                item.is_dir()
                and item.name not in ALWAYS_EXCLUDE_DIRS
                and item not in exclude_paths
            ):
                yield from walk_dir(item, parent_package=parent_package)

    yield from walk_dir(root, parent_package="")


def find_source_or_external_import(
    searched_symbol: str,
    search_module: str,
    module_lookup: dict[str, ast.Module],
) -> str | None:
    split = searched_symbol.rsplit(".", maxsplit=1)
    match split:
        case [symbol_object_name]:
            symbol_module_ref = None
        case [symbol_module_ref, symbol_object_name]:
            pass

    module = module_lookup.get(search_module)
    if not module:
        return ".".join((search_module, searched_symbol))

    # implementation in this mdule
    classes = filter_module_by_type(module, ast.ClassDef)
    for cd in classes:
        if cd.name == symbol_object_name:
            return ".".join((search_module, cd.name))

    # symbol is imported
    imports = resolve_import_statements(module)
    for imp in imports:
        if imp.name and imp.name == symbol_object_name:
            # name import
            return find_source_or_external_import(
                searched_symbol=imp.name,
                search_module=imp.module,
                module_lookup=module_lookup,
            )
        elif not imp.name and (
            imp.module == symbol_module_ref or imp.alias == symbol_module_ref
        ):
            # module import
            return find_source_or_external_import(
                searched_symbol=symbol_object_name,
                search_module=imp.module,
                module_lookup=module_lookup,
            )

    return None


def run(
    project_root: Path,
    exclude_relative: list[Path] | None,
) -> None:
    exclude_absolute: set[Path] = (
        {p.resolve() for p in exclude_relative} if exclude_relative else set()
    )

    module_hierarchy: dict[str, ast.Module] = {}
    for fqn, module in walk_project(
        root=project_root,
        exclude_paths=exclude_absolute,
    ):
        module_hierarchy[fqn] = module

    inheritance = InheritanceHierarchy()
    for fqn in module_hierarchy:
        module = module_hierarchy[fqn]
        classes = filter_module_by_type(module, ast.ClassDef)
        for class_def in classes:
            class_fqn = ".".join((fqn, class_def.name))
            bases = get_bases_from_class(class_def)
            for base in bases:
                parent = find_source_or_external_import(
                    searched_symbol=base,
                    search_module=fqn,
                    module_lookup=module_hierarchy,
                )
                if parent:
                    inheritance.add_relation(
                        parent=parent,
                        child=class_fqn,
                    )

    settings_subclasses = inheritance.transitive_subclasses(BASE_SETTINGS_FQN)
    fields_per_class: dict[str, list[SettingField]] = {}
    for fqn in sorted(settings_subclasses):
        module_part, class_part = fqn.rsplit(".", maxsplit=1)
        module = module_hierarchy[module_part]
        class_def = next(
            cd
            for cd in filter_module_by_type(module, ast.ClassDef)
            if cd.name == class_part
        )
        fields_per_class[class_def.name] = extract_fields_from_settings(
            class_def
        )

    env_example_txt = build_env_example(fields_per_class)
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
