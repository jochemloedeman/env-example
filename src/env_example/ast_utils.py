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

PYDANTIC_SETTINGS_PACKAGE = "pydantic_settings"
PYDANTIC_SETTINGS_BASE = "BaseSettings"
SETTINGS_CONFIG_CLASS = "SettingsConfigDict"
ENV_PREFIX_ARG = "env_prefix"


@dataclass
class SettingField:
    name: str
    settings_class: str
    prefix: str | None = None


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
