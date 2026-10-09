from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp, parse
from sqlglot.errors import ParseError

UNSAFE_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Merge,
    exp.Copy,
    exp.Transaction,
)
DANGEROUS_FUNCTIONS = {
    "load_extension",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "dblink",
    "dblink_exec",
    "lo_import",
    "lo_export",
    "set_config",
    "current_setting",
    "pg_sleep",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_terminate_backend",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "nextval",
    "setval",
    "readfile",
    "writefile",
}
SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "sqlite_schema", "sqlite_master"}


@dataclass
class SQLValidation:
    valid: bool
    normalized_sql: str | None = None
    errors: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)


class SQLValidator:
    def __init__(self, max_rows: int = 1000) -> None:
        self.max_rows = max_rows

    def validate(
        self,
        sql: str,
        dialect: str,
        allowed_tables: set[str],
        allowed_schemas: set[str] | None = None,
        allowed_columns: dict[str, set[str]] | None = None,
    ) -> SQLValidation:
        errors: list[str] = []
        try:
            statements = [item for item in parse(sql, read=dialect) if item is not None]
        except ParseError as exc:
            return SQLValidation(
                False,
                errors=[f"SQL could not be parsed: {exc.errors[0].get('description', str(exc))}"],
            )
        if len(statements) != 1:
            return SQLValidation(False, errors=["Exactly one SQL statement is allowed."])
        expression = statements[0]
        if not isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
            errors.append("Only read-only SELECT queries and SELECT-based CTEs are allowed.")
        if any(expression.find(node_type) for node_type in UNSAFE_EXPRESSIONS):
            errors.append("The query contains a data-changing or administrative operation.")
        if expression.find(exp.Into):
            errors.append("SELECT INTO is not allowed.")
        if expression.find(exp.Lock):
            errors.append("Row-locking SELECT statements are not allowed.")
        cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
        referenced: list[str] = []
        aliases: dict[str, str] = {}
        allowed_lower = {item.lower() for item in allowed_tables}
        schema_lower = {item.lower() for item in (allowed_schemas or set())}
        for table in expression.find_all(exp.Table):
            name = table.name
            schema_name = table.db
            if name.lower() in cte_names:
                continue
            referenced.append(name)
            aliases[(table.alias_or_name or name).lower()] = name.lower()
            if name.lower().startswith(("sqlite_", "pg_")) or name.lower() in SYSTEM_SCHEMAS:
                errors.append(f"System table access is not allowed: {name}.")
            elif name.lower() not in allowed_lower:
                errors.append(f"Table is not in the connection allowlist: {name}.")
            if schema_name:
                if schema_name.lower() in SYSTEM_SCHEMAS:
                    errors.append(f"System schema access is not allowed: {schema_name}.")
                elif schema_lower and schema_name.lower() not in schema_lower:
                    errors.append(f"Schema is not in the connection allowlist: {schema_name}.")
        for function in expression.find_all(exp.Func):
            function_name = (
                function.name if isinstance(function, exp.Anonymous) else function.sql_name()
            ).lower()
            if function_name in DANGEROUS_FUNCTIONS or function_name.startswith(
                ("pg_read_", "pg_ls_")
            ):
                errors.append(f"Dangerous database function is not allowed: {function_name}.")
        if allowed_columns:
            normalized_columns = {
                table.lower(): {column.lower() for column in columns}
                for table, columns in allowed_columns.items()
            }
            output_aliases = {
                alias.alias.lower() for alias in expression.find_all(exp.Alias) if alias.alias
            }
            base_tables = set(aliases.values())
            for column in expression.find_all(exp.Column):
                if column.name == "*" or column.name.lower() in output_aliases:
                    continue
                source = aliases.get(column.table.lower()) if column.table else None
                if source and column.name.lower() not in normalized_columns.get(source, set()):
                    errors.append(
                        f"Column does not exist on allowlisted table {source}: {column.name}."
                    )
                elif not column.table and len(base_tables) == 1:
                    source = next(iter(base_tables))
                    if column.name.lower() not in normalized_columns.get(source, set()):
                        errors.append(
                            f"Column does not exist on allowlisted table {source}: {column.name}."
                        )
        if errors:
            return SQLValidation(
                False, errors=list(dict.fromkeys(errors)), tables=sorted(set(referenced))
            )
        normalized = expression.sql(dialect=dialect, pretty=True)
        limited = f"SELECT * FROM ({normalized}) AS querymind_result LIMIT {self.max_rows + 1}"
        return SQLValidation(True, normalized_sql=limited, tables=sorted(set(referenced)))
