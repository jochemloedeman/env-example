import ast
from ast import (
    AnnAssign,
    Assign,
    Attribute,
    Call,
    ClassDef,
    Constant,
    Import,
    ImportFrom,
    Module,
    Name,
)
from dataclasses import dataclass
from typing import Callable

PYDANTIC_SETTINGS_PACKAGE = "pydantic_settings"
PYDANTIC_SETTINGS_BASE = "BaseSettings"
SETTINGS_CONFIG_CLASS = "SettingsConfigDict"
ENV_PREFIX_ARG = "env_prefix"


@dataclass
class SettingField:
    name: str
    settings_class: str
    prefix: str | None = None


def has_module_base(cd: ClassDef, module: Module) -> bool:
    """Check if class uses: import pydantic_settings; class X(pydantic_settings.BaseSettings)"""
    # Check for: import pydantic_settings
    has_module_import = any(
        isinstance(item, Import)
        and any(a.name == PYDANTIC_SETTINGS_PACKAGE for a in item.names)
        for item in module.body
    )
    if not has_module_import:
        return False

    # Check for: pydantic_settings.BaseSettings in bases
    has_qualified_base = any(
        isinstance(base, Attribute)
        and base.attr == PYDANTIC_SETTINGS_BASE
        and isinstance(base.value, Name)
        and base.value.id == PYDANTIC_SETTINGS_PACKAGE
        for base in cd.bases
    )
    return has_qualified_base


def has_absolute_base(cd: ClassDef, module: Module) -> bool:
    """Check if class uses: from pydantic_settings import BaseSettings; class X(BaseSettings)"""
    # Check for: from pydantic_settings import BaseSettings
    has_absolute_import = any(
        isinstance(item, ImportFrom)
        and item.module == PYDANTIC_SETTINGS_PACKAGE
        and any(name.name == PYDANTIC_SETTINGS_BASE for name in item.names)
        for item in module.body
    )
    if not has_absolute_import:
        return False

    # Check for: BaseSettings in bases
    has_direct_base = any(
        isinstance(base, Name) and base.id == PYDANTIC_SETTINGS_BASE
        for base in cd.bases
    )
    return has_direct_base


def has_alias_base(cd: ClassDef, module: Module) -> bool:
    """Check if class uses: import pydantic_settings as ps; class X(ps.BaseSettings)"""
    # Collect aliases for pydantic_settings
    aliases = [
        alias.asname
        for item in module.body
        if isinstance(item, Import)
        for alias in item.names
        if alias.name == PYDANTIC_SETTINGS_PACKAGE and alias.asname is not None
    ]
    if not aliases:
        return False

    # Check for: <alias>.BaseSettings in bases
    has_aliased_base = any(
        isinstance(base, Attribute)
        and base.attr == PYDANTIC_SETTINGS_BASE
        and isinstance(base.value, Name)
        and base.value.id in aliases
        for base in cd.bases
    )
    return has_aliased_base


BASE_CONDITIONS: list[Callable[[ClassDef, Module], bool]] = [
    has_absolute_base,
    has_module_base,
    has_alias_base,
]


def extract_settings_from_file(module_content: str) -> list[ClassDef]:
    module = ast.parse(module_content)
    defs = [
        item
        for item in module.body
        if isinstance(item, ClassDef)
        and any(condition(item, module) for condition in BASE_CONDITIONS)
    ]
    return defs


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
