"""init schema

Revision ID: 20260201_init_schema
Revises: 
Create Date: 2026-02-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260201_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tbl_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "DISABLED", name="user_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_permissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255)),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_user_roles",
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("role_id", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.ForeignKeyConstraint(["user_id"], ["tbl_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["tbl_roles.id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_role_permissions",
        sa.Column("role_id", sa.Integer, nullable=False),
        sa.Column("permission_id", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        sa.ForeignKeyConstraint(["role_id"], ["tbl_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["tbl_permissions.id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_symptoms",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("question_text", sa.String(255), nullable=False),
        sa.Column(
            "input_type",
            sa.Enum("BOOLEAN", "NUMBER", "TEXT", "SINGLE", name="symptom_input_type"),
            nullable=False,
        ),
        sa.Column("unit", sa.String(40)),
        sa.Column("options_json", sa.JSON),
        sa.Column("category", sa.String(80)),
        sa.Column("ui_section", sa.String(80)),
        sa.Column("parent_symptom_id", sa.Integer, nullable=True),
        sa.Column(
            "show_if_operator",
            sa.Enum("==", "!=", ">", "<", ">=", "<=", "PRESENT", "ABSENT", name="symptom_show_if_operator"),
            nullable=True,
        ),
        sa.Column("show_if_value", sa.String(120), nullable=True),
        sa.Column("priority_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("code", name="uq_symptoms_code"),
        sa.ForeignKeyConstraint(["parent_symptom_id"], ["tbl_symptoms.id"], ondelete="SET NULL"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_diseases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column(
            "urgency",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="disease_urgency"),
            nullable=False,
            server_default="LOW",
        ),
        sa.Column("advice", sa.Text),
        sa.Column("recommendations_json", sa.JSON),
        sa.Column(
            "severity",
            sa.Enum("INFO", "WARN", "DANGER", name="disease_severity"),
            nullable=False,
            server_default="INFO",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("code", name="uq_diseases_code"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule_code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("explanation_text", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("rule_code", name="uq_rules_code"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_rule_conditions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule_id", sa.Integer, nullable=False),
        sa.Column("symptom_id", sa.Integer, nullable=False),
        sa.Column(
            "operator",
            sa.Enum("PRESENT", "ABSENT", "==", "!=", ">=", "<=", ">", "<", name="rule_operator"),
            nullable=False,
        ),
        sa.Column("value", sa.String(120)),
        sa.Column("weight", sa.Numeric(6, 3), nullable=False, server_default="1.000"),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("rule_id", "symptom_id", name="uq_rule_symptom"),
        sa.ForeignKeyConstraint(["rule_id"], ["tbl_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["symptom_id"], ["tbl_symptoms.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_rule_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule_id", sa.Integer, nullable=False),
        sa.Column("disease_id", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.500"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("rule_id", "disease_id", name="uq_rule_disease"),
        sa.ForeignKeyConstraint(["rule_id"], ["tbl_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["disease_id"], ["tbl_diseases.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_assessments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column(
            "status",
            sa.Enum("IN_PROGRESS", "COMPLETED", name="assessment_status"),
            nullable=False,
            server_default="IN_PROGRESS",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["user_id"], ["tbl_users.id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_case_facts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("assessment_id", sa.Integer, nullable=False),
        sa.Column("symptom_id", sa.Integer, nullable=False),
        sa.Column("value_bool", sa.Boolean),
        sa.Column("value_number", sa.Numeric(10, 3)),
        sa.Column("value_text", sa.String(255)),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1.000"),
        sa.Column(
            "source",
            sa.Enum("USER", "DOCTOR", "SYSTEM", name="fact_source"),
            nullable=False,
            server_default="USER",
        ),
        sa.Column(
            "answered_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("assessment_id", "symptom_id", name="uq_assessment_symptom"),
        sa.ForeignKeyConstraint(["assessment_id"], ["tbl_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["symptom_id"], ["tbl_symptoms.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
    )

    op.create_table(
        "tbl_diagnosis_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("assessment_id", sa.Integer, nullable=False),
        sa.Column("disease_id", sa.Integer, nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="diagnosis_risk_level"),
        ),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("trace_json", sa.JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["tbl_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["disease_id"], ["tbl_diseases.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_runs_assessment", "tbl_diagnosis_runs", ["assessment_id"])
    op.create_index("ix_runs_disease", "tbl_diagnosis_runs", ["disease_id"])

    op.create_table(
        "tbl_audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("actor_user_id", sa.Integer),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity", sa.String(120), nullable=False),
        sa.Column("entity_id", sa.Integer),
        sa.Column("meta_json", sa.JSON),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["tbl_users.id"], ondelete="SET NULL"),
        mysql_engine="InnoDB",
    )
    op.create_index("ix_audit_actor", "tbl_audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_action", "tbl_audit_logs", ["action"])


def downgrade():
    op.drop_index("ix_audit_action", table_name="tbl_audit_logs")
    op.drop_index("ix_audit_actor", table_name="tbl_audit_logs")
    op.drop_table("tbl_audit_logs")

    op.drop_index("ix_runs_disease", table_name="tbl_diagnosis_runs")
    op.drop_index("ix_runs_assessment", table_name="tbl_diagnosis_runs")
    op.drop_table("tbl_diagnosis_runs")

    op.drop_table("tbl_case_facts")
    op.drop_table("tbl_assessments")
    op.drop_table("tbl_rule_actions")
    op.drop_table("tbl_rule_conditions")
    op.drop_table("tbl_rules")
    op.drop_table("tbl_diseases")
    op.drop_table("tbl_symptoms")
    op.drop_table("tbl_role_permissions")
    op.drop_table("tbl_user_roles")
    op.drop_table("tbl_permissions")
    op.drop_table("tbl_roles")
    op.drop_table("tbl_users")
