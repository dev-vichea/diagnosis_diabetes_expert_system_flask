from sqlalchemy import inspect, text

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from app import create_app
from app.extensions import db


def _table_columns(inspector, table_name):
    return {col["name"] for col in inspector.get_columns(table_name)}


def _has_unique(inspector, table_name, index_name):
    uniques = {uc["name"] for uc in inspector.get_unique_constraints(table_name)}
    if index_name in uniques:
        return True
    indexes = {
        idx["name"]
        for idx in inspector.get_indexes(table_name)
        if idx.get("unique")
    }
    return index_name in indexes


def _add_column(engine, table_name, column_name, column_def):
    inspector = inspect(engine)
    if column_name in _table_columns(inspector, table_name):
        return False
    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_def}"))
    db.session.commit()
    return True


def _ensure_unique(engine, table_name, index_name, columns_sql):
    inspector = inspect(engine)
    if _has_unique(inspector, table_name, index_name):
        return False
    dialect = engine.dialect.name
    if dialect == "sqlite":
        db.session.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns_sql})"))
    else:
        db.session.execute(text(f"ALTER TABLE {table_name} ADD UNIQUE INDEX {index_name} ({columns_sql})"))
    db.session.commit()
    return True


def main():
    if load_dotenv:
        load_dotenv()
    app = create_app()
    with app.app_context():
        engine = db.engine
        dialect = engine.dialect.name

        if dialect == "mysql":
            bool_type = "TINYINT(1)"
            json_type = "JSON"
            updated_at_def = "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        else:
            bool_type = "INTEGER"
            json_type = "TEXT"
            updated_at_def = "DATETIME"

        # tbl_symptoms
        _add_column(engine, "tbl_symptoms", "name", "name VARCHAR(160)")
        _add_column(engine, "tbl_symptoms", "input_type", "input_type VARCHAR(20) NOT NULL DEFAULT 'BOOLEAN'")
        _add_column(engine, "tbl_symptoms", "unit", "unit VARCHAR(40)")
        _add_column(engine, "tbl_symptoms", "options_json", f"options_json {json_type}")
        _add_column(engine, "tbl_symptoms", "is_derived", f"is_derived {bool_type} NOT NULL DEFAULT 0")
        _add_column(engine, "tbl_symptoms", "updated_at", f"updated_at {updated_at_def}")

        # tbl_rules
        _add_column(engine, "tbl_rules", "rule_code", "rule_code VARCHAR(80)")
        _add_column(engine, "tbl_rules", "title", "title VARCHAR(160)")
        _add_column(engine, "tbl_rules", "diagnosis", "diagnosis VARCHAR(120)")
        _add_column(engine, "tbl_rules", "confidence", "confidence INT")
        _add_column(engine, "tbl_rules", "explanation_text", "explanation_text TEXT")
        _add_column(engine, "tbl_rules", "updated_at", f"updated_at {updated_at_def}")
        _ensure_unique(engine, "tbl_rules", "uq_tbl_rules_rule_code", "rule_code")

        # tbl_rule_conditions
        _add_column(engine, "tbl_rule_conditions", "operator", "`operator` VARCHAR(8) NOT NULL DEFAULT '=='")
        _add_column(engine, "tbl_rule_conditions", "value", "`value` VARCHAR(120)")
        _add_column(engine, "tbl_rule_conditions", "logic_group", "logic_group VARCHAR(40)")

        # tbl_advices
        _add_column(engine, "tbl_advices", "recommendations_json", f"recommendations_json {json_type}")

        print("Schema patch complete.")


if __name__ == "__main__":
    main()
