import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from env_example.ast_utils import (
    SettingField,
    extract_fields_from_settings,
    get_bases_from_class,
)

ALWAYS_EXCLUDE_DIRS = {".venv", "site-packages"}
BASE_SETTINGS_FQN = "pydantic_settings.BaseSettings"


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


def _filter_module_by_type[T](module: ast.Module, type_: type[T]) -> list[T]:
    return [item for item in module.body if isinstance(item, type_)]


@dataclass
class Import:
    module: str
    name: str | None
    alias: str | None


def _resolve_name_imports(module: ast.Module) -> list[tuple[str, str]]:
    name_imports = _filter_module_by_type(module, ast.ImportFrom)
    fqns: list[tuple[str, str]] = []
    for ni in name_imports:
        if ni.module:
            # absolute import
            for name in ni.names:
                fqns.append((ni.module, name.name))
        else:
            raise NotImplementedError(
                "Resolving relative imports is not supported yet."
            )
    return fqns


def _resolve_module_imports(module: ast.Module) -> list[str]:
    module_imports = _filter_module_by_type(module, ast.Import)
    return [name.name for mi in module_imports for name in mi.names]


def resolve_import_statements(module: ast.Module) -> list[Import]:
    imports: list[Import] = []
    for item in module.body:
        if isinstance(item, ast.Import):
            imports.extend(
                [
                    Import(
                        module=name.name,
                        alias=name.asname,
                        name=None,
                    )
                    for name in item.names
                ]
            )
        elif isinstance(item, ast.ImportFrom):
            imports.extend(
                [
                    Import(
                        module=item.module, name=name.name, alias=name.asname
                    )
                    for name in item.names
                    if item.module
                ]
            )

    return imports


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
        case _:
            raise ValueError(
                f"{searched_symbol} is not a valid symbol in module {search_module}"
            )

    module = module_lookup.get(search_module)
    if not module:
        return ".".join((search_module, searched_symbol))

    # check if implementation is in the module itself
    classes = _filter_module_by_type(module, ast.ClassDef)
    for cd in classes:
        if cd.name == symbol_object_name:
            return ".".join((search_module, cd.name))

    # check if the symbol is imported
    imports = resolve_import_statements(module)
    for imp in imports:
        if imp.name and imp.name == symbol_object_name:
            return find_source_or_external_import(
                searched_symbol=imp.name,
                search_module=imp.module,
                module_lookup=module_lookup,
            )
        elif not imp.name and (
            imp.module == symbol_module_ref or imp.alias == symbol_module_ref
        ):
            return find_source_or_external_import(
                searched_symbol=symbol_object_name,
                search_module=imp.module,
                module_lookup=module_lookup,
            )

    return None


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
        classes = _filter_module_by_type(module, ast.ClassDef)
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
    fields: list[SettingField] = []
    for fqn in sorted(settings_subclasses):
        module_part, class_part = fqn.rsplit(".", maxsplit=1)
        module = module_hierarchy[module_part]
        class_def = next(
            cd
            for cd in _filter_module_by_type(module, ast.ClassDef)
            if cd.name == class_part
        )
        fields.extend(extract_fields_from_settings(class_def))

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
