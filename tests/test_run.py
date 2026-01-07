from collections import namedtuple
from pathlib import Path

import pytest

from env_example.main import run

Case = namedtuple("Case", ["name", "project_root", "exclude_dirs"])

test_cases: list[Case] = [
    Case(name="prefix", project_root=None, exclude_dirs=None),
    Case(name="alias_import", project_root=None, exclude_dirs=None),
    Case(name="module_import", project_root=None, exclude_dirs=None),
    Case(name="selective_import", project_root=None, exclude_dirs=None),
    Case(name="multiple_settings", project_root=None, exclude_dirs=None),
    Case(name="default_exclude", project_root=None, exclude_dirs=None),
    Case(name="user_exclude", project_root=None, exclude_dirs=["excluded"]),
]


@pytest.fixture
def test_case(request):
    """Parametrized fixture that provides the test case name"""
    return request.param


@pytest.fixture
def run_case(test_case):
    dir_arg = Path(__file__).parent / "cases" / f"{test_case.name}"
    run(dir_arg, exclude_dirs=test_case.exclude_dirs)
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
    fp = Path(__file__).parent / "cases" / f"{test_case.name}" / ".env.example"
    env_example_txt = fp.read_text()
    return env_example_txt


@pytest.mark.parametrize("test_case", test_cases, indirect=True)
def test_default(
    run_case,
    expected_env,
    outcome_env,
) -> None:
    assert outcome_env == expected_env
