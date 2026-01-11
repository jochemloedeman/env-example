import argparse
import ast
from ast import ClassDef, Import, ImportFrom, Module
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

ALWAYS_EXCLUDE_DIRS = {".venv", "site-packages"}
BASE_SETTINGS_FQN = "pydantic_settings.BaseSettings"


@dataclass
class ModuleContext:
    module: Module
    classes: dict[str, ClassDef]


def walk_project(
    root: Path,
    exclude_paths: set[Path],
) -> Iterator[tuple[str, ModuleContext]]:
    def walk_dir(
        dir: Path, parent_package: str
    ) -> Iterator[tuple[str, ModuleContext]]:
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

        for item in dir.iterdir():
            if item.is_file() and item.suffix == ".py":
                module = ast.parse(item.read_text())
                classes = {
                    body_item.name: body_item
                    for body_item in module.body
                    if isinstance(body_item, ClassDef)
                }
                module_name = item.name if item.stem != "__init__" else None
                module_fqn = ".".join(filter(None, [new_parent, module_name]))
                yield (
                    module_fqn,
                    ModuleContext(
                        module=module,
                        classes=classes,
                    ),
                )

            if (
                item.is_dir()
                and item.name not in ALWAYS_EXCLUDE_DIRS
                and item not in exclude_paths
            ):
                yield from walk_dir(item, parent_package=parent_package)

    yield from walk_dir(root, parent_package="")


def _filter_module_by_type[T](module: Module, type_: type[T]) -> list[T]:
    return [item for item in module.body if isinstance(item, type_)]


def _resolve_name_imports(module: Module) -> list[str]:
    name_imports = _filter_module_by_type(module, ImportFrom)
    fqns: list[str] = []
    for ni in name_imports:
        if ni.module:
            # absolute import
            for name in ni.names:
                fqns.append(".".join((ni.module, name.name)))
        else:
            raise NotImplementedError(
                "Resolving relative imports is not supported yet."
            )
    return []


def _resolve_module_imports(module: Module) -> list[str]:
    module_imports = _filter_module_by_type(module, Import)
    return [name.name for mi in module_imports for name in mi.names]


def find_implementation(
    symbol: str, module_mapping: dict[str, ModuleContext]
) -> str:
    return ""


def find_parent(
    class_def: ClassDef,
    class_fqn: str,
    module_hierarchy: dict[str, ModuleContext],
) -> str:
    return ""


class InheritanceHierarchy:
    def __init__(self) -> None:
        self._children: defaultdict[str, set] = defaultdict(set)

    def add_relation(self, parent: str, child: str):
        self._children[parent].add(child)

    def compute_transitive_closure(self) -> dict[str, str]:
        return {}


def run(
    project_root: Path,
    exclude_relative: list[Path] | None,
) -> None:
    exclude_absolute: set[Path] = (
        {p.resolve() for p in exclude_relative} if exclude_relative else set()
    )
    module_hierarchy: dict[str, ModuleContext] = {}
    for fqn, context in walk_project(
        root=project_root,
        exclude_paths=exclude_absolute,
    ):
        module_hierarchy[fqn] = context

    inheritance = InheritanceHierarchy()
    for fqn in module_hierarchy:
        mc = module_hierarchy[fqn]
        for class_fqn, class_def in mc.classes.items():
            parent = find_parent(
                class_def=class_def,
                class_fqn=class_fqn,
                module_hierarchy=module_hierarchy,
            )
            inheritance.add_relation(parent=parent, child=class_fqn)

    transitive_closure = inheritance.compute_transitive_closure()
    settings_fqns = transitive_closure[BASE_SETTINGS_FQN]
    settings_fqns


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
