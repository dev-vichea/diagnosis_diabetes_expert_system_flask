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


def _ensure_table(engine, table_name, create_sql):
    inspector = inspect(engine)
    if table_name in inspector.get_table_names():
        return False
    db.session.execute(text(create_sql))
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


def _ensure_index(engine, index_name, table_name, columns_sql):
    inspector = inspect(engine)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name in existing:
        return False
    dialect = engine.dialect.name
    if dialect == "sqlite":
        db.session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns_sql})"))
    else:
        db.session.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({columns_sql})"))
    db.session.commit()
    return True


def _drop_index(engine, table_name, index_name):
    inspector = inspect(engine)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name not in existing:
        return False
    dialect = engine.dialect.name
    if dialect == "sqlite":
        db.session.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
    else:
        db.session.execute(text(f"DROP INDEX {index_name} ON {table_name}"))
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
        _add_column(engine, "tbl_symptoms", "ui_section", "ui_section VARCHAR(80)")
        _add_column(engine, "tbl_symptoms", "parent_symptom_id", "parent_symptom_id INT")
        _add_column(engine, "tbl_symptoms", "show_if_operator", "show_if_operator VARCHAR(8)")
        _add_column(engine, "tbl_symptoms", "show_if_value", "show_if_value VARCHAR(120)")
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
        _add_column(engine, "tbl_rule_conditions", "is_required", f"is_required {bool_type} NOT NULL DEFAULT 1")
        _add_column(engine, "tbl_rule_conditions", "weight", "weight DOUBLE NOT NULL DEFAULT 1.0")

        # tbl_advices
        _add_column(engine, "tbl_advices", "recommendations_json", f"recommendations_json {json_type}")

        # tbl_assessment_metrics
        _add_column(engine, "tbl_assessment_metrics", "blood_sugar_bucket", "blood_sugar_bucket VARCHAR(40)")

        # tbl_assessment_answers
        _add_column(engine, "tbl_assessment_answers", "answer_text", "answer_text VARCHAR(255)")
        _add_column(engine, "tbl_assessment_answers", "answer_number", "answer_number DOUBLE")
        _add_column(engine, "tbl_assessment_answers", "answer_type", "answer_type VARCHAR(20) NOT NULL DEFAULT 'BOOLEAN'")
        _add_column(engine, "tbl_assessment_answers", "question_id", "question_id INT")
        _add_column(engine, "tbl_assessment_answers", "option_id", "option_id INT")

        # question group tables
        _ensure_table(
            engine,
            "tbl_question_groups",
            f"""
            CREATE TABLE tbl_question_groups (
                id INT AUTO_INCREMENT PRIMARY KEY,
                code VARCHAR(80) NOT NULL UNIQUE,
                title VARCHAR(160) NOT NULL,
                description TEXT,
                ui_section VARCHAR(80),
                is_active {bool_type} NOT NULL DEFAULT 1,
                priority_order INT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at {updated_at_def}
            )
            """
            if dialect == "mysql"
            else """
            CREATE TABLE tbl_question_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(80) NOT NULL UNIQUE,
                title VARCHAR(160) NOT NULL,
                description TEXT,
                ui_section VARCHAR(80),
                is_active INTEGER NOT NULL DEFAULT 1,
                priority_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )
            """
        )
        _ensure_table(
            engine,
            "tbl_question_group_items",
            """
            CREATE TABLE tbl_question_group_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INT NOT NULL,
                symptom_id INT NOT NULL,
                display_order INT NOT NULL DEFAULT 0,
                CONSTRAINT uq_question_group_symptom UNIQUE (group_id, symptom_id)
            )
            """
            if dialect == "sqlite"
            else """
            CREATE TABLE tbl_question_group_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                group_id INT NOT NULL,
                symptom_id INT NOT NULL,
                display_order INT NOT NULL DEFAULT 0,
                UNIQUE KEY uq_question_group_symptom (group_id, symptom_id)
            )
            """
        )
        _drop_index(engine, "tbl_question_group_items", "ix_question_group_items_group_id")
        _drop_index(engine, "tbl_question_group_items", "ix_question_group_items_symptom_id")
        _ensure_index(engine, "ix_question_group_items_group_id", "tbl_question_group_items", "group_id")
        _ensure_index(engine, "ix_question_group_items_symptom_id", "tbl_question_group_items", "symptom_id")

        # questions and options
        _ensure_table(
            engine,
            "tbl_questions",
            f"""
            CREATE TABLE tbl_questions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                code VARCHAR(80) NOT NULL UNIQUE,
                text VARCHAR(255) NOT NULL,
                question_type VARCHAR(20) NOT NULL DEFAULT 'SINGLE',
                help_text TEXT,
                order_group VARCHAR(40),
                fact_code VARCHAR(80),
                parent_question_id INT,
                trigger_operator VARCHAR(8) DEFAULT '==',
                trigger_value VARCHAR(120),
                is_active {bool_type} NOT NULL DEFAULT 1,
                priority_order INT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at {updated_at_def}
            )
            """
            if dialect == "mysql"
            else """
            CREATE TABLE tbl_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(80) NOT NULL UNIQUE,
                text VARCHAR(255) NOT NULL,
                question_type VARCHAR(20) NOT NULL DEFAULT 'SINGLE',
                help_text TEXT,
                order_group VARCHAR(40),
                fact_code VARCHAR(80),
                parent_question_id INT,
                trigger_operator VARCHAR(8) DEFAULT '==',
                trigger_value VARCHAR(120),
                is_active INTEGER NOT NULL DEFAULT 1,
                priority_order INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )
            """
        )
        _ensure_table(
            engine,
            "tbl_question_options",
            """
            CREATE TABLE tbl_question_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INT NOT NULL,
                code VARCHAR(80) NOT NULL,
                label VARCHAR(160) NOT NULL,
                value_text VARCHAR(120),
                value_number DOUBLE,
                display_order INT NOT NULL DEFAULT 0
            )
            """
            if dialect == "sqlite"
            else """
            CREATE TABLE tbl_question_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                question_id INT NOT NULL,
                code VARCHAR(80) NOT NULL,
                label VARCHAR(160) NOT NULL,
                value_text VARCHAR(120),
                value_number DOUBLE,
                display_order INT NOT NULL DEFAULT 0,
                UNIQUE KEY uq_question_option_code (question_id, code)
            )
            """
        )
        _drop_index(engine, "tbl_question_options", "ix_question_options_question_id")
        _ensure_index(engine, "ix_question_options_question_id", "tbl_question_options", "question_id")

        _ensure_table(
            engine,
            "tbl_option_fact_map",
            """
            CREATE TABLE tbl_option_fact_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                option_id INT NOT NULL,
                symptom_id INT NOT NULL,
                fact_value_bool INTEGER,
                fact_value_text VARCHAR(120),
                fact_value_number DOUBLE,
                weight DOUBLE NOT NULL DEFAULT 1.0
            )
            """
            if dialect == "sqlite"
            else """
            CREATE TABLE tbl_option_fact_map (
                id INT AUTO_INCREMENT PRIMARY KEY,
                option_id INT NOT NULL,
                symptom_id INT NOT NULL,
                fact_value_bool TINYINT(1),
                fact_value_text VARCHAR(120),
                fact_value_number DOUBLE,
                weight DOUBLE NOT NULL DEFAULT 1.0
            )
            """
        )
        _drop_index(engine, "tbl_option_fact_map", "ix_option_fact_map_option_id")
        _drop_index(engine, "tbl_option_fact_map", "ix_option_fact_map_symptom_id")
        _ensure_index(engine, "ix_option_fact_map_option_id", "tbl_option_fact_map", "option_id")
        _ensure_index(engine, "ix_option_fact_map_symptom_id", "tbl_option_fact_map", "symptom_id")

        print("Schema patch complete.")


if __name__ == "__main__":
    main()
