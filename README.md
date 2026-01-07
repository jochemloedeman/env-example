<div align="center">

<h1>
  <br/>env-example
</h1>

</div>

Creates an `.env.example` file for your monorepo, based on all [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) classes found in your project. Env-example uses the abstract syntax tree of your project instead of runtime introspection, to avoid side effects and be less prone to import errors.

# Usage
I recommend to use `uvx` to run `env-example`:
```bash
# Basic usage
uvx env-example

# Exclude specific directories relative to the project root
uvx env-example --exclude-dir other/scripts
```
