# env-example
[![PyPI - Project version](https://img.shields.io/pypi/v/env-example?logo=pypi)][pypi]
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/env-example)][pypi]
[![PyPI - License](https://img.shields.io/pypi/l/env-example)][license]

Creates an `.env.example` file for your monorepo, based on all Pydantic settings classes found in your project.

# Usage
I recommend to use `uvx` to run `env-example`:
```bash
# Uses the current directory
uvx env-example

# For a specific directory
uvx env-example --project-root /path/to/your/project

# Exclude specific directories
uvx env-example --exclude_dir tests --exclude_dir scripts
```
