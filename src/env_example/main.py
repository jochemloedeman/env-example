import argparse
import ast
from ast import (
    AnnAssign,
    Assign,
    Attribute,
    Call,
    ClassDef,
    Constant,
    Dict,
    Name,
)
from collections import defaultdict
from dataclasses import dataclass, field
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
class ModuleImport:
    module: str
    alias: str | None = None


@dataclass(frozen=True)
class NameImport:
    module: str | None
    name: str
    level: int
    alias: str | None = None

    def __post_init__(self):
        if not self.module and not self.level:
            raise ValueError("Absolute imports must have a module component")

    def get_qualified_parent_module(
        self,
        current: QualifiedName,
    ) -> QualifiedName:
        """Resolve the qualified parent module for a relative import"""
        if not self.level:
            assert self.module
            return QualifiedName.from_str(self.module)

        parent_qn = current
        for _ in range(self.level):
            parent_qn = parent_qn.parent

        if not self.module:
            return parent_qn

        return parent_qn.child(self.module)


type ImportItem = ModuleImport | NameImport


@dataclass(frozen=True)
class ParsedModule:
    ast_module: ast.Module
    classes: dict[str, ast.ClassDef]


@dataclass
class ParsedSettings:
    prefix: str | None = None
    fields: set[str] = field(default_factory=set)


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
    """
    Orchestrator function.
    1. Parse the modules and map the package structure of the project
    2. Build a class inheritance lookup
    3. Parse settings for the subclasses of BaseSettings
    4. Write them to an .env.example file
    """
    exclude_absolute: set[Path] = (
        {p.resolve() for p in exclude_relative} if exclude_relative else set()
    )

    module_lookup: dict[QualifiedName, ParsedModule] = {}
    for fqn, ast_module in walk_project(
        root=project_root,
        exclude_paths=exclude_absolute,
    ):
        classes = filter_module_by_type(ast_module, ast.ClassDef)
        module_lookup[fqn] = ParsedModule(
            ast_module=ast_module,
            classes={cd.name: cd for cd in classes},
        )

    child_lookup: defaultdict[QualifiedName, list[QualifiedName]] = (
        defaultdict(list)
    )
    for fqn, parsed_module in module_lookup.items():
        for class_def in parsed_module.classes.values():
            class_fqn = fqn.child(class_def.name)
            for base in get_bases_from_class(class_def):
                parent = find_source_or_external_import(
                    searched_symbol=base,
                    search_module=fqn,
                    module_lookup=module_lookup,
                )
                if parent:
                    child_lookup[parent].append(class_fqn)

    parsed_settings = defaultdict(ParsedSettings)
    children = child_lookup[BASE_SETTINGS_FQN]
    for child in children:
        gather_settings_for_subtree(
            node=child,
            child_lookup=child_lookup,
            module_lookup=module_lookup,
            parsed_settings=parsed_settings,
        )

    env_example_txt = build_env_example(parsed_settings)
    if env_example_txt:
        (project_root / OUTPUT_FILE).write_text(env_example_txt)


def walk_project(
    root: Path,
    exclude_paths: set[Path],
) -> Iterator[tuple[QualifiedName, ast.Module]]:
    """
    Walks down the directory structure of the project, and
    returns parsed modules and their names with the respect to
    the package namespace.
    """

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
            if item.is_file() and item.suffix == ".py":
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
                yield from walk_dir(item, parent_package=new_parent)

    yield from walk_dir(root, parent_package=QualifiedName(()))


def gather_settings_for_subtree(
    node: QualifiedName,
    child_lookup: defaultdict[QualifiedName, list[QualifiedName]],
    module_lookup: dict[QualifiedName, ParsedModule],
    parsed_settings: defaultdict[QualifiedName, ParsedSettings],
) -> None:
    """
    Recursively parses fieldsfrom settings classes and adds them to
    an aggregator for both the currently considered class and its children.
    """
    class_def = module_lookup[node.parent].classes[node.leaf]
    fields = parse_fields_from_settings(class_def)
    prefix = parse_settings_prefix(class_def)

    parsed_settings[node].prefix = prefix
    parsed_settings[node].fields.update(fields)

    for child in child_lookup[node]:
        # add parent fields for the child settings class
        parsed_settings[child].fields.update(parsed_settings[node].fields)

        gather_settings_for_subtree(
            node=child,
            child_lookup=child_lookup,
            module_lookup=module_lookup,
            parsed_settings=parsed_settings,
        )


def find_source_or_external_import(
    searched_symbol: QualifiedName,
    search_module: QualifiedName,
    module_lookup: dict[QualifiedName, ParsedModule],
) -> QualifiedName | None:
    """
    Returns either
        - the fqn when the import is external
        - the fqn to the implementation of the searched symbol
        - None if none of the above, and no imports can be followed
    """
    *module_parts, symbol_object_name = searched_symbol.parts
    symbol_module_ref = ".".join(module_parts) or None

    parsed_module = module_lookup.get(search_module)

    # module is external
    if not parsed_module:
        return search_module.child(str(searched_symbol))

    # implementation is in module
    if symbol_object_name in parsed_module.classes:
        return search_module.child(symbol_object_name)

    # follow imports
    imports = resolve_import_statements(parsed_module.ast_module)
    for imp in imports:
        match imp:
            case NameImport(module, name) if name == symbol_object_name:
                resolved = imp.get_qualified_parent_module(
                    current=search_module
                )
                return find_source_or_external_import(
                    searched_symbol=QualifiedName((name,)),
                    search_module=resolved,
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


def build_env_example(
    parsed_settings: dict[QualifiedName, ParsedSettings],
) -> str:
    if not parsed_settings:
        return ""
    sections = [
        f"# {qn.leaf}\n"
        + "\n".join(
            f"{parsed.prefix or ''}{field}=".upper()
            for field in sorted(parsed.fields)
        )
        for qn, parsed in sorted(
            parsed_settings.items(), key=lambda x: x[0].leaf
        )
    ]
    return "\n\n".join(sections) + "\n"


def parse_settings_prefix(cd: ClassDef) -> str | None:
    """
    Parses the model_config configuration to find the configured
    prefix. model_config can be given as a SettingConfigDict and
    as a plain dict. we cover both cases.
    """
    prefixes: list[str] = []

    for item in cd.body:
        if isinstance(item, AnnAssign):
            target = item.target
            value = item.value
        elif isinstance(item, Assign) and len(item.targets) == 1:
            target = item.targets[0]
            value = item.value
        else:
            continue

        if not (isinstance(target, Name) and target.id == "model_config"):
            continue

        if isinstance(value, Call):
            # SettingsConfigDict case
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

        elif isinstance(value, Dict):
            # plain dict case
            for key, val in zip(value.keys, value.values):
                if (
                    isinstance(key, Constant)
                    and key.value == ENV_PREFIX_ARG
                    and isinstance(val, Constant)
                    and isinstance(val.value, str)
                ):
                    prefixes.append(val.value)

    if len(prefixes) > 1:
        raise ValueError(
            f"Multiple prefixes found for class {cd.name}: {prefixes}"
        )

    prefix = prefixes[0] if prefixes else None
    return prefix


def parse_fields_from_settings(cd: ClassDef) -> list[str]:
    fields: list[str] = []

    for elem in cd.body:
        if not isinstance(elem, AnnAssign):
            continue
        if not isinstance(elem.target, Name):
            continue
        name: str = elem.target.id
        fields.append(name)

    return fields


def get_bases_from_class(cd: ClassDef) -> list[QualifiedName]:
    bases: list[QualifiedName] = []
    for base in cd.bases:
        if isinstance(base, Name):
            bases.append(QualifiedName((base.id,)))
        elif isinstance(base, Attribute):
            parts: list[str] = [base.attr]
            node = base.value
            while isinstance(node, Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, Name):
                parts.append(node.id)
                bases.append(QualifiedName(tuple(reversed(parts))))
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
        elif isinstance(item, ast.ImportFrom):
            imports.extend(
                NameImport(
                    module=item.module,
                    name=name.name,
                    alias=name.asname,
                    level=item.level,
                )
                for name in item.names
            )

    return imports


if __name__ == "__main__":
    main()
