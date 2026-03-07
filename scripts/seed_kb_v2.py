from pathlib import Path
import argparse
import sys

from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed KB v2 blueprint")
    parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Mark symptoms/rules/diseases not in blueprint as inactive",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    load_dotenv(dotenv_path=repo_root / ".env", override=False)

    from app import create_app
    from app.seed_kb_v2 import seed_kb_v2

    app = create_app()
    with app.app_context():
        seed_kb_v2(deactivate_missing=args.deactivate_missing)


if __name__ == "__main__":
    main()
