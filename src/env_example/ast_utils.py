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
from functools import partial
from typing import Callable, Iterator

PYDANTIC_SETTINGS_PACKAGE = "pydantic_settings"
PYDANTIC_SETTINGS_BASE = "BaseSettings"
SETTINGS_CONFIG_CLASS = "SettingsConfigDict"
ENV_PREFIX_ARG = "env_prefix"


@dataclass
class ClassContext:
    class_def: ClassDef
    module: Module
    package: str | None


@dataclass
class SettingField:
    name: str
    settings_class: str
    prefix: str | None = None


def has_module_base(
    cd: ClassDef,
    module: Module,
    import_package: str,
    import_class: str,
) -> bool:
    """Check if class uses: import pydantic_settings; class X(pydantic_settings.BaseSettings)"""
    # Check for: import pydantic_settings
    has_module_import = any(
        isinstance(item, Import)
        and any(a.name == import_package for a in item.names)
        for item in module.body
    )
    if not has_module_import:
        return False

    # Check for: pydantic_settings.BaseSettings in bases
    has_qualified_base = any(
        isinstance(base, Attribute)
        and base.attr == import_class
        and isinstance(base.value, Name)
        and base.value.id == import_package
        for base in cd.bases
    )
    return has_qualified_base


def has_absolute_import_base(
    cd: ClassDef,
    module: Module,
    import_package: str,
    import_class: str,
) -> bool:
    """Check if class uses: from pydantic_settings import BaseSettings; class X(BaseSettings)"""
    # Check for: from pydantic_settings import BaseSettings
    has_absolute_import = any(
        isinstance(item, ImportFrom)
        and item.module == import_package
        and any(name.name == import_class for name in item.names)
        for item in module.body
    )
    if not has_absolute_import:
        return False

    # Check for: BaseSettings in bases
    has_direct_base = any(
        isinstance(base, Name) and base.id == import_class for base in cd.bases
    )
    return has_direct_base


def has_alias_base(
    cd: ClassDef,
    module: Module,
    import_package: str,
    import_class: str,
) -> bool:
    """Check if class uses: import pydantic_settings as ps; class X(ps.BaseSettings)"""
    # Collect aliases for pydantic_settings
    aliases = [
        alias.asname
        for item in module.body
        if isinstance(item, Import)
        for alias in item.names
        if alias.name == import_package and alias.asname is not None
    ]
    if not aliases:
        return False

    # Check for: <alias>.BaseSettings in bases
    has_aliased_base = any(
        isinstance(base, Attribute)
        and base.attr == import_class
        and isinstance(base.value, Name)
        and base.value.id in aliases
        for base in cd.bases
    )
    return has_aliased_base


def has_transitive_base(
    cd: ClassDef, module: Module, direct_settings: list[ClassContext]
) -> bool:
    return any(
        has_absolute_import_base(
            cd=cd,
            module=module,
            import_package=ds.package,
            import_class=ds.class_def.name,
        )
        for ds in direct_settings
    )


DIRECT_INHERITANCE_CONDITIONS: list[Callable[[ClassDef, Module], bool]] = [
    partial(
        has_absolute_import_base,
        import_package=PYDANTIC_SETTINGS_PACKAGE,
        import_class=PYDANTIC_SETTINGS_BASE,
    ),
    partial(
        has_module_base,
        import_package=PYDANTIC_SETTINGS_PACKAGE,
        import_class=PYDANTIC_SETTINGS_BASE,
    ),
    partial(
        has_alias_base,
        import_module=PYDANTIC_SETTINGS_PACKAGE,
        import_class=PYDANTIC_SETTINGS_BASE,
    ),
]


def extract_class_contexts(
    module_content: str, package: str | None
) -> Iterator[ClassContext]:
    module = ast.parse(module_content)
    for item in module.body:
        if isinstance(item, ClassDef):
            yield ClassContext(
                class_def=item,
                module=module,
                package=package,
            )


def extract_settings(
    contexts: list[ClassContext],
) -> list[ClassDef]:
    direct_contexts: list[ClassContext] = [
        context
        for context in contexts
        if any(
            condition(context.class_def, context.module)
            for condition in DIRECT_INHERITANCE_CONDITIONS
        )
    ]
    direct_settings = [context.class_def for context in direct_contexts]
    transitive_settings = [
        context.class_def
        for context in contexts
        if has_transitive_base(
            cd=context.class_def,
            module=context.module,
            direct_settings=direct_contexts,
        )
    ]
    return [*direct_settings, *transitive_settings]


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
