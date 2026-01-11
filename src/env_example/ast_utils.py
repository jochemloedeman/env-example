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
from typing import Iterator

PYDANTIC_SETTINGS_PACKAGE = "pydantic_settings"
PYDANTIC_SETTINGS_BASE = "BaseSettings"
SETTINGS_CONFIG_CLASS = "SettingsConfigDict"
ENV_PREFIX_ARG = "env_prefix"


@dataclass
class ModuleContext:
    module: Module
    classes: list[ClassDef]
    package: str


@dataclass
class SettingField:
    name: str
    settings_class: str
    prefix: str | None = None


def _has_qualified_base(
    class_def: ClassDef,
    base_class: str,
    base_package: str,
) -> bool:
    return any(
        isinstance(base, Attribute)
        and base.attr == base_class
        and isinstance(base.value, Name)
        and base.value.id == base_package
        for base in class_def.bases
    )


def _has_full_import(module: Module, import_name: str) -> bool:
    return any(
        isinstance(item, Import)
        and any(a.name == import_name for a in item.names)
        for item in module.body
    )


def extract_children_with_module_import_base(
    context: ModuleContext,
    import_class: str,
    import_package: str,
) -> list[ClassDef]:
    if not _has_full_import(context.module, import_package):
        return []

    children = [
        c
        for c in context.classes
        if _has_qualified_base(
            class_def=c, base_class=import_class, base_package=import_package
        )
    ]
    return children


def _has_selective_import(
    module: Module,
    import_name: str,
    from_name: str,
) -> bool:
    return any(
        isinstance(item, ImportFrom)
        and item.module == from_name
        and any(name.name == import_name for name in item.names)
        for item in module.body
    )


def extract_children_with_class_import_base(
    context: ModuleContext,
    import_class: str,
    import_package: str,
) -> list[ClassDef]:
    if not _has_selective_import(
        context.module,
        import_name=import_class,
        from_name=import_package,
    ):
        return []

    children = [
        c for c in context.classes if _has_direct_base(c, import_class)
    ]

    return children


def _has_direct_base(class_def: ClassDef, base_class: str) -> bool:
    return any(
        isinstance(base, Name) and base.id == base_class
        for base in class_def.bases
    )


def get_package_aliases(module: Module, package: str) -> list[str]:
    return [
        alias.asname
        for item in module.body
        if isinstance(item, Import)
        for alias in item.names
        if alias.name == package and alias.asname is not None
    ]


def _has_aliased_base(
    class_def: ClassDef,
    aliased_package: str,
    base_class: str,
) -> bool:
    return any(
        isinstance(base, Attribute)
        and base.attr == base_class
        and isinstance(base.value, Name)
        and base.value.id == aliased_package
        for base in class_def.bases
    )


def extract_children_with_package_alias_base(
    context: ModuleContext,
    import_class: str,
    import_package: str,
) -> list[ClassDef]:
    aliases = get_package_aliases(
        context.module,
        import_package,
    )
    if not aliases:
        return []

    children = [
        c
        for c in context.classes
        if any(
            _has_aliased_base(
                class_def=c,
                aliased_package=ap,
                base_class=import_class,
            )
            for ap in aliases
        )
    ]

    return children


# def has_transitive_base(
#     cd: ClassDef, module: Module, direct_settings: list[ModuleContext]
# ) -> bool:
#     return any(
#         has_absolute_import_base(
#             cd=cd,
#             module=module,
#             import_package=ds.package,
#             import_class="",
#         )
#         for ds in direct_settings
#     )


def extract_module_contexts(
    module_content: str, package: str
) -> Iterator[ModuleContext]:
    module = ast.parse(module_content)
    classes = [item for item in module.body if isinstance(item, ClassDef)]
    yield ModuleContext(
        module=module,
        classes=classes,
        package=package,
    )


@dataclass
class ClassContext:
    class_def: ClassDef
    module: Module


def extract_settings(
    module_contexts: list[ModuleContext],
) -> list[ClassDef]:
    # direct inheritance settings
    class_import = [
        cd
        for context in module_contexts
        for cd in extract_children_with_class_import_base(
            context=context,
            import_class=PYDANTIC_SETTINGS_BASE,
            import_package=PYDANTIC_SETTINGS_PACKAGE,
        )
    ]
    module_import = [
        cd
        for context in module_contexts
        for cd in extract_children_with_module_import_base(
            context=context,
            import_class=PYDANTIC_SETTINGS_BASE,
            import_package=PYDANTIC_SETTINGS_PACKAGE,
        )
    ]
    aliased_module_import = [
        cd
        for context in module_contexts
        for cd in extract_children_with_package_alias_base(
            context=context,
            import_class=PYDANTIC_SETTINGS_BASE,
            import_package=PYDANTIC_SETTINGS_PACKAGE,
        )
    ]
    direct_settings: list[ClassDef] = [
        *class_import,
        *module_import,
        *aliased_module_import,
    ]

    # same-module transitive inheritance

    # same-package transitive inheritance

    return [*direct_settings]


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
