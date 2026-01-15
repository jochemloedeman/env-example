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
from dataclasses import dataclass
from enum import Enum

PYDANTIC_SETTINGS_PACKAGE = "pydantic_settings"
PYDANTIC_SETTINGS_BASE = "BaseSettings"
SETTINGS_CONFIG_CLASS = "SettingsConfigDict"
ENV_PREFIX_ARG = "env_prefix"


class ImportType(Enum):
    NAME = "name"
    MODULE = "module"


@dataclass
class SettingField:
    name: str
    settings_class: str
    prefix: str | None = None


@dataclass
class ImportItem:
    module: str
    name: str | None
    alias: str | None


def resolve_import_statements(module: ast.Module) -> list[ImportItem]:
    imports: list[ImportItem] = []
    for item in module.body:
        if isinstance(item, ast.Import):
            imports.extend(
                [
                    ImportItem(
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
                    ImportItem(
                        module=item.module,
                        name=name.name,
                        alias=name.asname,
                    )
                    for name in item.names
                    if item.module
                ]
            )

    return imports


def filter_module_by_type[T](module: ast.Module, type_: type[T]) -> list[T]:
    return [item for item in module.body if isinstance(item, type_)]


def get_bases_from_class(cd: ClassDef) -> list[str]:
    bases: list[str] = []
    for base in cd.bases:
        if isinstance(base, Name):
            # bare name
            bases.append(base.id)
        elif isinstance(base, Attribute) and isinstance(base.value, Name):
            # qualified name
            bases.append(".".join((base.value.id, base.attr)))
    return bases


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
