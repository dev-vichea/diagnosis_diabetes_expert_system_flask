"""align findings, assessments, rules, and result schemas

Revision ID: 20260225_core_schema_v2
Revises: 20260225_disease_outcome
Create Date: 2026-02-25 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260225_core_schema_v2"
down_revision = "20260225_disease_outcome"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}


def _foreign_key_exists(table_name: str, fk_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return fk_name in {fk.get("name") for fk in inspector.get_foreign_keys(table_name)}


def upgrade():
    bind = op.get_bind()

    if _table_exists("tbl_symptoms"):
        if _column_exists("tbl_symptoms", "is_active") and not _column_exists("tbl_symptoms", "active"):
            op.alter_column(
                "tbl_symptoms",
                "is_active",
                new_column_name="active",
                existing_type=sa.Boolean(),
                existing_nullable=False,
            )
        elif not _column_exists("tbl_symptoms", "active"):
            op.add_column(
                "tbl_symptoms",
                sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            )

        if not _column_exists("tbl_symptoms", "min_value"):
            op.add_column("tbl_symptoms", sa.Column("min_value", sa.Numeric(10, 3), nullable=True))
        if not _column_exists("tbl_symptoms", "max_value"):
            op.add_column("tbl_symptoms", sa.Column("max_value", sa.Numeric(10, 3), nullable=True))
        if not _column_exists("tbl_symptoms", "allow_unknown"):
            op.add_column(
                "tbl_symptoms",
                sa.Column("allow_unknown", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )
        if not _column_exists("tbl_symptoms", "importance_weight"):
            op.add_column(
                "tbl_symptoms",
                sa.Column("importance_weight", sa.Numeric(6, 3), nullable=False, server_default="1.000"),
            )
        if not _column_exists("tbl_symptoms", "reference_ranges_json"):
            op.add_column("tbl_symptoms", sa.Column("reference_ranges_json", sa.JSON(), nullable=True))

        bind.execute(
            sa.text(
                """
                ALTER TABLE tbl_symptoms
                MODIFY COLUMN input_type ENUM('BOOLEAN','NUMBER','TEXT','SINGLE','MULTI') NOT NULL
                """
            )
        )

    if _table_exists("tbl_assessments"):
        if not _column_exists("tbl_assessments", "patient_id"):
            op.add_column("tbl_assessments", sa.Column("patient_id", sa.Integer(), nullable=True))
        if not _column_exists("tbl_assessments", "engine_version"):
            op.add_column("tbl_assessments", sa.Column("engine_version", sa.String(length=40), nullable=True))
        if _column_exists("tbl_assessments", "user_id"):
            bind.execute(
                sa.text(
                    """
                    UPDATE tbl_assessments
                    SET patient_id = user_id
                    WHERE patient_id IS NULL
                    """
                )
            )
        if not _index_exists("tbl_assessments", "ix_assessments_patient_id"):
            op.create_index("ix_assessments_patient_id", "tbl_assessments", ["patient_id"])
        if not _foreign_key_exists("tbl_assessments", "fk_assessments_patient_id"):
            op.create_foreign_key(
                "fk_assessments_patient_id",
                "tbl_assessments",
                "tbl_users",
                ["patient_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if _table_exists("tbl_case_facts"):
        if _column_exists("tbl_case_facts", "answered_at") and not _column_exists("tbl_case_facts", "created_at"):
            op.alter_column(
                "tbl_case_facts",
                "answered_at",
                new_column_name="created_at",
                existing_type=sa.DateTime(),
                existing_nullable=False,
            )
        elif not _column_exists("tbl_case_facts", "created_at"):
            op.add_column(
                "tbl_case_facts",
                sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            )

        if not _column_exists("tbl_case_facts", "finding_code"):
            op.add_column("tbl_case_facts", sa.Column("finding_code", sa.String(length=80), nullable=True))
        if not _column_exists("tbl_case_facts", "value_json"):
            op.add_column("tbl_case_facts", sa.Column("value_json", sa.JSON(), nullable=True))
        if not _column_exists("tbl_case_facts", "state"):
            op.add_column(
                "tbl_case_facts",
                sa.Column(
                    "state",
                    sa.Enum("true", "false", "unknown", name="assessment_answer_state"),
                    nullable=False,
                    server_default="unknown",
                ),
            )
        if not _column_exists("tbl_case_facts", "is_provided"):
            op.add_column(
                "tbl_case_facts",
                sa.Column("is_provided", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )

        bind.execute(
            sa.text(
                """
                UPDATE tbl_case_facts cf
                JOIN tbl_symptoms s ON s.id = cf.symptom_id
                SET cf.finding_code = s.code
                WHERE cf.finding_code IS NULL OR cf.finding_code = ''
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE tbl_case_facts
                SET is_provided = CASE
                    WHEN value_bool IS NOT NULL OR value_number IS NOT NULL OR (value_text IS NOT NULL AND value_text <> '') OR value_json IS NOT NULL
                    THEN 1 ELSE 0
                END
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE tbl_case_facts
                SET state = CASE
                    WHEN value_bool = 1 THEN 'true'
                    WHEN value_bool = 0 THEN 'false'
                    WHEN value_number IS NOT NULL OR (value_text IS NOT NULL AND value_text <> '') OR value_json IS NOT NULL THEN 'true'
                    ELSE 'unknown'
                END
                """
            )
        )
        if not _index_exists("tbl_case_facts", "ix_case_facts_finding_code"):
            op.create_index("ix_case_facts_finding_code", "tbl_case_facts", ["finding_code"])

    if not _table_exists("tbl_rule_sets"):
        op.create_table(
            "tbl_rule_sets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint("version", name="uq_rule_sets_version"),
            mysql_engine="InnoDB",
        )
    bind.execute(
        sa.text(
            """
            INSERT INTO tbl_rule_sets (version, active, released_at, notes)
            SELECT 1, 1, CURRENT_TIMESTAMP, 'Default ruleset'
            WHERE NOT EXISTS (SELECT 1 FROM tbl_rule_sets)
            """
        )
    )

    if _table_exists("tbl_rules"):
        if _column_exists("tbl_rules", "is_active") and not _column_exists("tbl_rules", "active"):
            op.alter_column(
                "tbl_rules",
                "is_active",
                new_column_name="active",
                existing_type=sa.Boolean(),
                existing_nullable=False,
            )
        elif not _column_exists("tbl_rules", "active"):
            op.add_column(
                "tbl_rules",
                sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            )

        if _column_exists("tbl_rules", "stop_on_match") and not _column_exists("tbl_rules", "stop_engine_on_match"):
            op.alter_column(
                "tbl_rules",
                "stop_on_match",
                new_column_name="stop_engine_on_match",
                existing_type=sa.Boolean(),
                existing_nullable=False,
                existing_server_default=sa.text("0"),
            )
        elif not _column_exists("tbl_rules", "stop_engine_on_match"):
            op.add_column(
                "tbl_rules",
                sa.Column("stop_engine_on_match", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )

        if _column_exists("tbl_rules", "confidence_cap_if_unconfirmed") and not _column_exists("tbl_rules", "max_conf_without_labs"):
            op.alter_column(
                "tbl_rules",
                "confidence_cap_if_unconfirmed",
                new_column_name="max_conf_without_labs",
                existing_type=sa.Numeric(4, 3),
                existing_nullable=True,
            )
        elif not _column_exists("tbl_rules", "max_conf_without_labs"):
            op.add_column("tbl_rules", sa.Column("max_conf_without_labs", sa.Numeric(4, 3), nullable=True))

        if not _column_exists("tbl_rules", "rule_set_id"):
            op.add_column("tbl_rules", sa.Column("rule_set_id", sa.Integer(), nullable=True))
        if not _index_exists("tbl_rules", "ix_tbl_rules_rule_set_id"):
            op.create_index("ix_tbl_rules_rule_set_id", "tbl_rules", ["rule_set_id"])

        bind.execute(
            sa.text(
                """
                UPDATE tbl_rules r
                JOIN (
                    SELECT id
                    FROM tbl_rule_sets
                    WHERE active = 1
                    ORDER BY version DESC, id DESC
                    LIMIT 1
                ) rs
                SET r.rule_set_id = rs.id
                WHERE r.rule_set_id IS NULL
                """
            )
        )
        if not _foreign_key_exists("tbl_rules", "fk_rules_rule_set_id"):
            op.create_foreign_key(
                "fk_rules_rule_set_id",
                "tbl_rules",
                "tbl_rule_sets",
                ["rule_set_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if _table_exists("tbl_rule_conditions"):
        if not _column_exists("tbl_rule_conditions", "finding_code"):
            op.add_column("tbl_rule_conditions", sa.Column("finding_code", sa.String(length=80), nullable=True))
        if not _column_exists("tbl_rule_conditions", "values_json"):
            op.add_column("tbl_rule_conditions", sa.Column("values_json", sa.JSON(), nullable=True))
        if not _column_exists("tbl_rule_conditions", "score_points"):
            op.add_column(
                "tbl_rule_conditions",
                sa.Column("score_points", sa.Integer(), nullable=False, server_default="0"),
            )
        if not _column_exists("tbl_rule_conditions", "negate"):
            op.add_column(
                "tbl_rule_conditions",
                sa.Column("negate", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )

        bind.execute(
            sa.text(
                """
                UPDATE tbl_rule_conditions rc
                JOIN tbl_symptoms s ON s.id = rc.symptom_id
                SET rc.finding_code = s.code
                WHERE rc.finding_code IS NULL OR rc.finding_code = ''
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE tbl_rule_conditions
                SET values_json = JSON_ARRAY(value)
                WHERE values_json IS NULL AND value IS NOT NULL
                """
            )
        )
        bind.execute(
            sa.text(
                """
                ALTER TABLE tbl_rule_conditions
                MODIFY COLUMN operator ENUM('PRESENT','ABSENT','==','!=','>=','<=','>','<','EQ','GTE','BETWEEN','IN') NOT NULL
                """
            )
        )
        if not _index_exists("tbl_rule_conditions", "ix_rule_conditions_finding_code"):
            op.create_index("ix_rule_conditions_finding_code", "tbl_rule_conditions", ["finding_code"])

    if not _table_exists("tbl_assessment_rule_results"):
        op.create_table(
            "tbl_assessment_rule_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("assessment_id", sa.Integer(), nullable=False),
            sa.Column("rule_id", sa.Integer(), nullable=False),
            sa.Column(
                "matched_state",
                sa.Enum("match", "no_match", "unknown", name="assessment_rule_match_state"),
                nullable=False,
                server_default="unknown",
            ),
            sa.Column("score_added", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("confidence_added", sa.Numeric(6, 3), nullable=False, server_default="0.000"),
            sa.Column("missing_findings_json", sa.JSON(), nullable=True),
            sa.Column("explain_text", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(["assessment_id"], ["tbl_assessments.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["rule_id"], ["tbl_rules.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("assessment_id", "rule_id", name="uq_assessment_rule_result"),
            mysql_engine="InnoDB",
        )
        op.create_index("ix_assessment_rule_results_assessment", "tbl_assessment_rule_results", ["assessment_id"])
        op.create_index("ix_assessment_rule_results_rule", "tbl_assessment_rule_results", ["rule_id"])

    if _table_exists("tbl_assessment_diagnosis_results"):
        if _column_exists("tbl_assessment_diagnosis_results", "score") and not _column_exists("tbl_assessment_diagnosis_results", "score_total"):
            op.alter_column(
                "tbl_assessment_diagnosis_results",
                "score",
                new_column_name="score_total",
                existing_type=sa.Integer(),
                existing_nullable=False,
            )
        elif not _column_exists("tbl_assessment_diagnosis_results", "score_total"):
            op.add_column("tbl_assessment_diagnosis_results", sa.Column("score_total", sa.Integer(), nullable=False, server_default="0"))

        if _column_exists("tbl_assessment_diagnosis_results", "trace_json") and not _column_exists("tbl_assessment_diagnosis_results", "top_evidence_json"):
            op.alter_column(
                "tbl_assessment_diagnosis_results",
                "trace_json",
                new_column_name="top_evidence_json",
                existing_type=sa.JSON(),
                existing_nullable=False,
            )
        elif not _column_exists("tbl_assessment_diagnosis_results", "top_evidence_json"):
            op.add_column("tbl_assessment_diagnosis_results", sa.Column("top_evidence_json", sa.JSON(), nullable=False))

        if not _column_exists("tbl_assessment_diagnosis_results", "status"):
            op.add_column(
                "tbl_assessment_diagnosis_results",
                sa.Column(
                    "status",
                    sa.Enum("confirmed", "high", "possible", "unlikely", name="diagnosis_result_status"),
                    nullable=True,
                ),
            )
        if not _column_exists("tbl_assessment_diagnosis_results", "confirmed_by_rule_id"):
            op.add_column("tbl_assessment_diagnosis_results", sa.Column("confirmed_by_rule_id", sa.Integer(), nullable=True))
        if not _column_exists("tbl_assessment_diagnosis_results", "missing_key_facts_json"):
            op.add_column("tbl_assessment_diagnosis_results", sa.Column("missing_key_facts_json", sa.JSON(), nullable=True))

        bind.execute(
            sa.text(
                """
                UPDATE tbl_assessment_diagnosis_results
                SET status = CASE
                    WHEN UPPER(COALESCE(evidence_level, 'LOW')) = 'HIGH' THEN 'high'
                    WHEN UPPER(COALESCE(evidence_level, 'LOW')) = 'MODERATE' THEN 'possible'
                    ELSE 'unlikely'
                END
                WHERE status IS NULL
                """
            )
        )
        if not _foreign_key_exists("tbl_assessment_diagnosis_results", "fk_assessment_diag_confirmed_rule"):
            op.create_foreign_key(
                "fk_assessment_diag_confirmed_rule",
                "tbl_assessment_diagnosis_results",
                "tbl_rules",
                ["confirmed_by_rule_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if not _index_exists("tbl_assessment_diagnosis_results", "ix_assessment_diag_results_status"):
            op.create_index("ix_assessment_diag_results_status", "tbl_assessment_diagnosis_results", ["status"])


def downgrade():
    if _table_exists("tbl_assessment_diagnosis_results"):
        if _index_exists("tbl_assessment_diagnosis_results", "ix_assessment_diag_results_status"):
            op.drop_index("ix_assessment_diag_results_status", table_name="tbl_assessment_diagnosis_results")
        if _foreign_key_exists("tbl_assessment_diagnosis_results", "fk_assessment_diag_confirmed_rule"):
            op.drop_constraint("fk_assessment_diag_confirmed_rule", "tbl_assessment_diagnosis_results", type_="foreignkey")
        if _column_exists("tbl_assessment_diagnosis_results", "missing_key_facts_json"):
            op.drop_column("tbl_assessment_diagnosis_results", "missing_key_facts_json")
        if _column_exists("tbl_assessment_diagnosis_results", "confirmed_by_rule_id"):
            op.drop_column("tbl_assessment_diagnosis_results", "confirmed_by_rule_id")
        if _column_exists("tbl_assessment_diagnosis_results", "status"):
            op.drop_column("tbl_assessment_diagnosis_results", "status")
        if _column_exists("tbl_assessment_diagnosis_results", "top_evidence_json") and not _column_exists("tbl_assessment_diagnosis_results", "trace_json"):
            op.alter_column(
                "tbl_assessment_diagnosis_results",
                "top_evidence_json",
                new_column_name="trace_json",
                existing_type=sa.JSON(),
                existing_nullable=False,
            )
        if _column_exists("tbl_assessment_diagnosis_results", "score_total") and not _column_exists("tbl_assessment_diagnosis_results", "score"):
            op.alter_column(
                "tbl_assessment_diagnosis_results",
                "score_total",
                new_column_name="score",
                existing_type=sa.Integer(),
                existing_nullable=False,
            )

    if _table_exists("tbl_assessment_rule_results"):
        if _index_exists("tbl_assessment_rule_results", "ix_assessment_rule_results_rule"):
            op.drop_index("ix_assessment_rule_results_rule", table_name="tbl_assessment_rule_results")
        if _index_exists("tbl_assessment_rule_results", "ix_assessment_rule_results_assessment"):
            op.drop_index("ix_assessment_rule_results_assessment", table_name="tbl_assessment_rule_results")
        op.drop_table("tbl_assessment_rule_results")

    if _table_exists("tbl_rule_conditions"):
        if _index_exists("tbl_rule_conditions", "ix_rule_conditions_finding_code"):
            op.drop_index("ix_rule_conditions_finding_code", table_name="tbl_rule_conditions")
        if _column_exists("tbl_rule_conditions", "negate"):
            op.drop_column("tbl_rule_conditions", "negate")
        if _column_exists("tbl_rule_conditions", "score_points"):
            op.drop_column("tbl_rule_conditions", "score_points")
        if _column_exists("tbl_rule_conditions", "values_json"):
            op.drop_column("tbl_rule_conditions", "values_json")
        if _column_exists("tbl_rule_conditions", "finding_code"):
            op.drop_column("tbl_rule_conditions", "finding_code")
        op.get_bind().execute(
            sa.text(
                """
                ALTER TABLE tbl_rule_conditions
                MODIFY COLUMN operator ENUM('PRESENT','ABSENT','==','!=','>=','<=','>','<') NOT NULL
                """
            )
        )

    if _table_exists("tbl_rules"):
        if _foreign_key_exists("tbl_rules", "fk_rules_rule_set_id"):
            op.drop_constraint("fk_rules_rule_set_id", "tbl_rules", type_="foreignkey")
        if _index_exists("tbl_rules", "ix_tbl_rules_rule_set_id"):
            op.drop_index("ix_tbl_rules_rule_set_id", table_name="tbl_rules")
        if _column_exists("tbl_rules", "rule_set_id"):
            op.drop_column("tbl_rules", "rule_set_id")
        if _column_exists("tbl_rules", "max_conf_without_labs") and not _column_exists("tbl_rules", "confidence_cap_if_unconfirmed"):
            op.alter_column(
                "tbl_rules",
                "max_conf_without_labs",
                new_column_name="confidence_cap_if_unconfirmed",
                existing_type=sa.Numeric(4, 3),
                existing_nullable=True,
            )
        if _column_exists("tbl_rules", "stop_engine_on_match") and not _column_exists("tbl_rules", "stop_on_match"):
            op.alter_column(
                "tbl_rules",
                "stop_engine_on_match",
                new_column_name="stop_on_match",
                existing_type=sa.Boolean(),
                existing_nullable=False,
            )
        if _column_exists("tbl_rules", "active") and not _column_exists("tbl_rules", "is_active"):
            op.alter_column(
                "tbl_rules",
                "active",
                new_column_name="is_active",
                existing_type=sa.Boolean(),
                existing_nullable=False,
            )

    if _table_exists("tbl_rule_sets"):
        op.drop_table("tbl_rule_sets")

    if _table_exists("tbl_case_facts"):
        if _index_exists("tbl_case_facts", "ix_case_facts_finding_code"):
            op.drop_index("ix_case_facts_finding_code", table_name="tbl_case_facts")
        if _column_exists("tbl_case_facts", "is_provided"):
            op.drop_column("tbl_case_facts", "is_provided")
        if _column_exists("tbl_case_facts", "state"):
            op.drop_column("tbl_case_facts", "state")
        if _column_exists("tbl_case_facts", "value_json"):
            op.drop_column("tbl_case_facts", "value_json")
        if _column_exists("tbl_case_facts", "finding_code"):
            op.drop_column("tbl_case_facts", "finding_code")
        if _column_exists("tbl_case_facts", "created_at") and not _column_exists("tbl_case_facts", "answered_at"):
            op.alter_column(
                "tbl_case_facts",
                "created_at",
                new_column_name="answered_at",
                existing_type=sa.DateTime(),
                existing_nullable=False,
            )

    if _table_exists("tbl_assessments"):
        if _foreign_key_exists("tbl_assessments", "fk_assessments_patient_id"):
            op.drop_constraint("fk_assessments_patient_id", "tbl_assessments", type_="foreignkey")
        if _index_exists("tbl_assessments", "ix_assessments_patient_id"):
            op.drop_index("ix_assessments_patient_id", table_name="tbl_assessments")
        if _column_exists("tbl_assessments", "engine_version"):
            op.drop_column("tbl_assessments", "engine_version")
        if _column_exists("tbl_assessments", "patient_id"):
            op.drop_column("tbl_assessments", "patient_id")

    if _table_exists("tbl_symptoms"):
        if _column_exists("tbl_symptoms", "reference_ranges_json"):
            op.drop_column("tbl_symptoms", "reference_ranges_json")
        if _column_exists("tbl_symptoms", "importance_weight"):
            op.drop_column("tbl_symptoms", "importance_weight")
        if _column_exists("tbl_symptoms", "allow_unknown"):
            op.drop_column("tbl_symptoms", "allow_unknown")
        if _column_exists("tbl_symptoms", "max_value"):
            op.drop_column("tbl_symptoms", "max_value")
        if _column_exists("tbl_symptoms", "min_value"):
            op.drop_column("tbl_symptoms", "min_value")
        op.get_bind().execute(
            sa.text(
                """
                ALTER TABLE tbl_symptoms
                MODIFY COLUMN input_type ENUM('BOOLEAN','NUMBER','TEXT','SINGLE') NOT NULL
                """
            )
        )
        if _column_exists("tbl_symptoms", "active") and not _column_exists("tbl_symptoms", "is_active"):
            op.alter_column(
                "tbl_symptoms",
                "active",
                new_column_name="is_active",
                existing_type=sa.Boolean(),
                existing_nullable=False,
            )
