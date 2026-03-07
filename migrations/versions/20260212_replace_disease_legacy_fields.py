"""replace legacy disease fields with profile schema

Revision ID: 20260212_disease_replace
Revises: 20260212_disease_profile
Create Date: 2026-02-12 23:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260212_disease_replace"
down_revision = "20260212_disease_profile"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    query = sa.text(
        """
        SELECT COUNT(*) AS count_value
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
          AND COLUMN_NAME = :column_name
        """
    )
    return bool(
        bind.execute(
            query,
            {"table_name": table_name, "column_name": column_name},
        ).scalar()
    )


def upgrade():
    bind = op.get_bind()

    has_urgency = _column_exists("tbl_diseases", "urgency")
    has_advice = _column_exists("tbl_diseases", "advice")
    has_severity = _column_exists("tbl_diseases", "severity")
    has_recommendations = _column_exists("tbl_diseases", "recommendations_json")

    if has_urgency:
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET severity_level =
                    CASE UPPER(COALESCE(urgency, 'LOW'))
                        WHEN 'HIGH' THEN 'HIGH'
                        WHEN 'MEDIUM' THEN 'MEDIUM'
                        ELSE 'LOW'
                    END
                WHERE severity_level IS NULL
                   OR UPPER(severity_level) NOT IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')
                """
            )
        )

    if has_severity:
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET severity_level =
                    CASE UPPER(COALESCE(severity, 'INFO'))
                        WHEN 'DANGER' THEN 'HIGH'
                        WHEN 'WARN' THEN 'MEDIUM'
                        ELSE COALESCE(severity_level, 'LOW')
                    END
                WHERE UPPER(COALESCE(severity_level, 'LOW')) = 'LOW'
                """
            )
        )

    if has_advice:
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET description = COALESCE(NULLIF(description, ''), advice)
                WHERE advice IS NOT NULL AND advice <> ''
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE tbl_diseases
                SET default_next_steps = COALESCE(NULLIF(default_next_steps, ''), advice)
                WHERE advice IS NOT NULL AND advice <> ''
                """
            )
        )

    bind.execute(
        sa.text(
            """
            UPDATE tbl_diseases
            SET patient_label_confirmed = COALESCE(NULLIF(patient_label_confirmed, ''), name)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE tbl_diseases
            SET patient_label_screening = COALESCE(NULLIF(patient_label_screening, ''), CONCAT('Possible ', name, ' (screening)'))
            """
        )
    )

    if has_recommendations:
        op.drop_column("tbl_diseases", "recommendations_json")
    if has_advice:
        op.drop_column("tbl_diseases", "advice")
    if has_severity:
        op.drop_column("tbl_diseases", "severity")
    if has_urgency:
        op.drop_column("tbl_diseases", "urgency")


def downgrade():
    if not _column_exists("tbl_diseases", "urgency"):
        op.add_column(
            "tbl_diseases",
            sa.Column(
                "urgency",
                sa.Enum("LOW", "MEDIUM", "HIGH", name="disease_urgency"),
                nullable=False,
                server_default="LOW",
            ),
        )
    if not _column_exists("tbl_diseases", "advice"):
        op.add_column("tbl_diseases", sa.Column("advice", sa.Text(), nullable=True))
    if not _column_exists("tbl_diseases", "recommendations_json"):
        op.add_column("tbl_diseases", sa.Column("recommendations_json", sa.JSON(), nullable=True))
    if not _column_exists("tbl_diseases", "severity"):
        op.add_column(
            "tbl_diseases",
            sa.Column(
                "severity",
                sa.Enum("INFO", "WARN", "DANGER", name="disease_severity"),
                nullable=False,
                server_default="INFO",
            ),
        )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE tbl_diseases
            SET urgency =
                CASE UPPER(COALESCE(severity_level, 'LOW'))
                    WHEN 'URGENT' THEN 'HIGH'
                    WHEN 'HIGH' THEN 'HIGH'
                    WHEN 'MEDIUM' THEN 'MEDIUM'
                    ELSE 'LOW'
                END
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE tbl_diseases
            SET severity =
                CASE UPPER(COALESCE(severity_level, 'LOW'))
                    WHEN 'URGENT' THEN 'DANGER'
                    WHEN 'HIGH' THEN 'DANGER'
                    WHEN 'MEDIUM' THEN 'WARN'
                    ELSE 'INFO'
                END
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE tbl_diseases
            SET advice = COALESCE(NULLIF(description, ''), default_next_steps)
            """
        )
    )
