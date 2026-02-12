from dataclasses import dataclass
from pathlib import Path

import pytest

from env_example.main import generate_env_example


@dataclass
class Case:
    name: str
    exclude_dirs: list[str] | None = None
    ignore_optionals: bool = False


test_cases: list[Case] = [
    Case(name="prefix"),
    Case(name="alias_import"),
    Case(name="module_import"),
    Case(name="selective_import"),
    Case(name="multiple_settings"),
    Case(name="default_exclude"),
    Case(name="transitive_inheritance"),
    Case(name="two_level_transitive_inheritance"),
    Case(name="reexport_inheritance"),
    Case(name="qualified_module_import"),
    Case(name="relative_import"),
    Case(name="main_file"),
    Case(
        name="user_exclude",
        exclude_dirs=[
            "package/excluded",
            "package/other_excluded",
            "package/included/nested_excluded",
        ],
    ),
    Case(name="optional_fields", ignore_optionals=True),
]


@pytest.fixture
def test_case(request):
    """Parametrized fixture that provides the test case name"""
    return request.param


@pytest.fixture
def run_case(test_case):
    dir_arg = Path(__file__).parent / "cases" / f"{test_case.name}" / "project"
    exclude_paths = (
        [dir_arg / p for p in test_case.exclude_dirs]
        if test_case.exclude_dirs
        else None
    )
    generate_env_example(
        project_root=dir_arg,
        exclude_relative=exclude_paths,
        ignore_optionals=test_case.ignore_optionals,
    )
    yield
    example_file = dir_arg / ".env.example"
    example_file.unlink()


@pytest.fixture
def expected_env(test_case):
    fp = (
        Path(__file__).parent
        / "cases"
        / f"{test_case.name}"
        / ".env.example.expected"
    )
    env_example_txt = fp.read_text()
    return env_example_txt


@pytest.fixture
def outcome_env(test_case, run_case):
    fp = (
        Path(__file__).parent
        / "cases"
        / f"{test_case.name}"
        / "project"
        / ".env.example"
    )
    env_example_txt = fp.read_text()
    return env_example_txt


@pytest.mark.parametrize(
    "test_case",
    test_cases,
    indirect=True,
    ids=[case.name for case in test_cases],
)
def test_generate_env_example(
    run_case,
    expected_env,
    outcome_env,
) -> None:
    assert outcome_env == expected_env


def test_no_settings_no_file_created() -> None:
    project_dir = Path(__file__).parent / "cases" / "no_settings" / "project"
    example_file = project_dir / ".env.example"

    generate_env_example(
        project_root=project_dir,
        exclude_relative=None,
        ignore_optionals=False,
    )

    try:
        assert not example_file.exists()
    finally:
        example_file.unlink(missing_ok=True)


def test_multiple_prefixes_raises_error() -> None:
    project_dir = (
        Path(__file__).parent / "cases" / "multiple_prefixes" / "project"
    )

    with pytest.raises(ValueError, match="Multiple prefixes found"):
        generate_env_example(
            project_root=project_dir,
            exclude_relative=None,
            ignore_optionals=False,
        )
