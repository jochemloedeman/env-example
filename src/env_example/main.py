import argparse
import ast
from ast import (
    AnnAssign,
    Assign,
    Attribute,
    Call,
    ClassDef,
    Constant,
    Name,
)
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Self

ALWAYS_EXCLUDE_DIRS = {".venv", "site-packages"}
SETTINGS_CONFIG_CLASS = "SettingsConfigDict"
ENV_PREFIX_ARG = "env_prefix"
OUTPUT_FILE = ".env.example"


@dataclass(frozen=True)
class QualifiedName:
    parts: tuple[str, ...]

    @classmethod
    def from_str(cls, fqn: str) -> Self:
        return cls(tuple(fqn.split(".")))

    @property
    def parent(self) -> Self:
        return self.__class__(self.parts[:-1])

    @property
    def leaf(self) -> str:
        return self.parts[-1]

    def child(self, name: str) -> Self:
        return self.__class__(self.parts + (name,))

    def __str__(self) -> str:
        return ".".join(self.parts)

    def __lt__(self, other: Self) -> bool:
        return self.parts < other.parts


BASE_SETTINGS_FQN = QualifiedName(("pydantic_settings", "BaseSettings"))


@dataclass(frozen=True)
class SettingField:
    name: str
    settings_class: str
    prefix: str | None = None


@dataclass(frozen=True)
class ModuleImport:
    module: str
    alias: str | None = None


@dataclass(frozen=True)
class NameImport:
    module: str
    name: str
    alias: str | None = None


type ImportItem = ModuleImport | NameImport


@dataclass(frozen=True)
class ParsedModule:
    ast_module: ast.Module
    classes: dict[str, ast.ClassDef]


class InheritanceHierarchy:
    def __init__(self) -> None:
        self._children: defaultdict[QualifiedName, set[QualifiedName]] = (
            defaultdict(set)
        )

    def add_relation(self, parent: QualifiedName, child: QualifiedName):
        self._children[parent].add(child)

    def transitive_subclasses(
        self, class_name: QualifiedName
    ) -> set[QualifiedName]:
        reachable = set()
        for child in self._children[class_name]:
            reachable.add(child)
            reachable.update(self.transitive_subclasses(child))
        return reachable


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
    generate_env_example(
        project_root=cwd,
        exclude_relative=namespace.exclude_dir,
    )


def generate_env_example(
    project_root: Path,
    exclude_relative: list[Path] | None,
) -> None:
    exclude_absolute: set[Path] = (
        {p.resolve() for p in exclude_relative} if exclude_relative else set()
    )

    module_hierarchy: dict[QualifiedName, ParsedModule] = {}
    for fqn, ast_module in walk_project(
        root=project_root,
        exclude_paths=exclude_absolute,
    ):
        classes = filter_module_by_type(ast_module, ast.ClassDef)
        module_hierarchy[fqn] = ParsedModule(
            ast_module=ast_module,
            classes={cd.name: cd for cd in classes},
        )

    inheritance = InheritanceHierarchy()
    for fqn, parsed_module in module_hierarchy.items():
        for class_def in parsed_module.classes.values():
            class_fqn = fqn.child(class_def.name)
            for base in get_bases_from_class(class_def):
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
        class_def = module_hierarchy[fqn.parent].classes[fqn.leaf]
        fields_per_class[class_def.name] = extract_fields_from_settings(
            class_def
        )

    env_example_txt = build_env_example(fields_per_class)
    write_to_file(env_example_txt, project_root / OUTPUT_FILE)


def write_to_file(text: str, file: Path) -> None:
    file.write_text(text)


def walk_project(
    root: Path,
    exclude_paths: set[Path],
) -> Iterator[tuple[QualifiedName, ast.Module]]:
    def walk_dir(
        dir: Path, parent_package: QualifiedName
    ) -> Iterator[tuple[QualifiedName, ast.Module]]:
        is_package = False
        for p in dir.iterdir():
            if p.name == "__init__.py":
                is_package = True
                break

        new_parent = (
            parent_package.child(dir.name) if is_package else QualifiedName(())
        )

        for item in sorted(dir.iterdir()):
            if is_package and item.is_file() and item.suffix == ".py":
                module = ast.parse(item.read_text())
                module_fqn = (
                    new_parent
                    if item.stem == "__init__"
                    else new_parent.child(item.stem)
                )
                yield (module_fqn, module)

            if (
                item.is_dir()
                and item.name not in ALWAYS_EXCLUDE_DIRS
                and item not in exclude_paths
            ):
                yield from walk_dir(item, parent_package=parent_package)

    yield from walk_dir(root, parent_package=QualifiedName(()))


def find_source_or_external_import(
    searched_symbol: QualifiedName,
    search_module: QualifiedName,
    module_lookup: dict[QualifiedName, ParsedModule],
) -> QualifiedName | None:
    match searched_symbol.parts:
        case (symbol_object_name,):
            symbol_module_ref = None
        case (*_, symbol_module_ref, symbol_object_name):
            pass

    parsed_module = module_lookup.get(search_module)
    if not parsed_module:
        return search_module.child(str(searched_symbol))

    if symbol_object_name in parsed_module.classes:
        return search_module.child(symbol_object_name)

    imports = resolve_import_statements(parsed_module.ast_module)
    for imp in imports:
        match imp:
            case NameImport(module, name, _) if name == symbol_object_name:
                return find_source_or_external_import(
                    searched_symbol=QualifiedName((name,)),
                    search_module=QualifiedName.from_str(module),
                    module_lookup=module_lookup,
                )
            case ModuleImport(module, alias) if (
                module == symbol_module_ref or alias == symbol_module_ref
            ):
                return find_source_or_external_import(
                    searched_symbol=QualifiedName((symbol_object_name,)),
                    search_module=QualifiedName.from_str(module),
                    module_lookup=module_lookup,
                )

    return None


def build_env_example(fields_per_class: dict[str, list[SettingField]]) -> str:
    sections = [
        f"# {class_name}\n"
        + "\n".join(
            f"{field.prefix or ''}{field.name}=".upper() for field in fields
        )
        for class_name, fields in fields_per_class.items()
    ]
    return "\n\n".join(sections) + "\n"


def extract_fields_from_settings(cd: ClassDef) -> list[SettingField]:
    prefixes: list[str] = []

    for item in cd.body:
        if not isinstance(item, (Assign, AnnAssign)):
            continue

        value = item.value
        if not isinstance(value, Call):
            continue

        if not (
            isinstance(value.func, Name)
            and value.func.id == SETTINGS_CONFIG_CLASS
        ):
            continue

        for kw in value.keywords:
            if (
                kw.arg == ENV_PREFIX_ARG
                and isinstance(kw.value, Constant)
                and isinstance(kw.value.value, str)
            ):
                prefixes.append(kw.value.value)

    if len(prefixes) > 1:
        raise ValueError("Multiple prefixes found, invalid.")

    prefix = prefixes[0] if prefixes else None
    fields: list[SettingField] = []

    for elem in cd.body:
        if not isinstance(elem, AnnAssign):
            continue
        if not isinstance(elem.target, Name):
            continue
        name: str = elem.target.id
        fields.append(
            SettingField(
                name=name,
                settings_class=cd.name,
                prefix=prefix,
            )
        )

    return fields


def get_bases_from_class(cd: ClassDef) -> list[QualifiedName]:
    bases: list[QualifiedName] = []
    for base in cd.bases:
        if isinstance(base, Name):
            bases.append(QualifiedName((base.id,)))
        elif isinstance(base, Attribute) and isinstance(base.value, Name):
            bases.append(QualifiedName((base.value.id, base.attr)))
    return bases


def filter_module_by_type[T](module: ast.Module, type_: type[T]) -> list[T]:
    return [item for item in module.body if isinstance(item, type_)]


def resolve_import_statements(module: ast.Module) -> list[ImportItem]:
    imports: list[ImportItem] = []
    for item in module.body:
        if isinstance(item, ast.Import):
            imports.extend(
                ModuleImport(module=name.name, alias=name.asname)
                for name in item.names
            )
        elif isinstance(item, ast.ImportFrom) and item.module:
            imports.extend(
                NameImport(
                    module=item.module, name=name.name, alias=name.asname
                )
                for name in item.names
            )

    return imports


if __name__ == "__main__":
    main()
