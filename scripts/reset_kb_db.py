import os
import sys

if __name__ == "__main__":
    from dotenv import load_dotenv

    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    env_path = os.path.join(root_path, ".env")
    load_dotenv(env_path, override=True)

from app import create_app
from app.extensions import db
from app.models import Assessment, CaseFact, DiagnosisRun, Disease, Rule, RuleAction, RuleCondition, Symptom


RESET_ORDER = [
    DiagnosisRun,
    CaseFact,
    Assessment,
    RuleCondition,
    RuleAction,
    Rule,
    Symptom,
    Disease,
]


def reset_kb_db() -> None:
    print("Resetting KB + assessment data...")
    for model in RESET_ORDER:
        deleted = db.session.query(model).delete(synchronize_session=False)
        print(f"  - {model.__tablename__}: {deleted} row(s)")
    db.session.commit()
    print("KB reset complete.")


def main() -> None:
    app = create_app()
    with app.app_context():
        reset_kb_db()


if __name__ == "__main__":
    main()
