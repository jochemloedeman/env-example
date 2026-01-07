from pathlib import Path

import pytest

from env_example.main import run

test_cases = [
    "prefix",
    "alias_import",
    "module_import",
    "selective_import",
    "multiple_settings",
]


@pytest.fixture
def test_case(request):
    """Parametrized fixture that provides the test case name"""
    return request.param


@pytest.fixture
def run_env_example(test_case):
    dir = Path(__file__).parent / "cases" / f"{test_case}"
    dir_arg = dir.as_posix()
    run(dir_arg)
    yield
    example_file = dir / ".env.example"
    example_file.unlink()


@pytest.fixture
def expected_env(test_case):
    fp = (
        Path(__file__).parent
        / "cases"
        / f"{test_case}"
        / ".env.example.expected"
    )
    env_example_txt = fp.read_text()
    return env_example_txt


@pytest.fixture
def outcome_env(test_case, run_env_example):
    fp = Path(__file__).parent / "cases" / f"{test_case}" / ".env.example"
    env_example_txt = fp.read_text()
    return env_example_txt


@pytest.mark.parametrize("test_case", test_cases, indirect=True)
def test_prefix(
    run_env_example,
    expected_env,
    outcome_env,
) -> None:
    assert outcome_env == expected_env
