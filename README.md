<div align="center">
<h1>
  env-example
</h1>
</div>
<p align="center">
<a href="https://pypi.org/project/fastapi" target="_blank">
    <img src="https://img.shields.io/pypi/v/env-example?color=%2334D058&label=pypi%20package" alt="Package version">
</a>
<a href="https://pypi.org/project/fastapi" target="_blank">
    <img src="https://github.com/jochemloedeman/env-example/actions/workflows/test.yml/badge.svg" alt="Package version">
</a>
</p>


Creates an `.env.example` file for your Python monorepo, based on all [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) classes found in your project. Env-example uses the abstract syntax tree of your project to discover settings instead of runtime introspection, to avoid side effects and having to deal with external project dependencies.

# Usage
I recommend to use `uvx` to run `env-example`:
```bash
# Basic usage
uvx env-example

# Exclude specific directories relative to the project root
uvx env-example --exclude-dir other/scripts
```

# Example
```python
from pydantic import BaseSettings


class AppSettings(BaseSettings):
    model_config = {
        "env_prefix": "APP__"
    }
    debug: bool
    log_level: str

class DatabaseSettings(BaseSettings):
    model_config = {
        "env_prefix": "DB__"
    }
    host: str
    port: int
    username: str
    password: str
```

env-example will generate the following `.env.example` file:
```shell
# AppSettings
APP__DEBUG=
APP__LOG_LEVEL=

# DatabaseSettings
DB__HOST=
DB__PORT=
DB__USERNAME=
DB__PASSWORD=
```
