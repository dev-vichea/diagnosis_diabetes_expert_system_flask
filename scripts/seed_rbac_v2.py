from pathlib import Path
import sys

from dotenv import load_dotenv

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    load_dotenv(dotenv_path=repo_root / ".env", override=False)
    from app import create_app
    from app.seed_rbac_v2 import seed_roles_permissions_v2
    app = create_app()
    with app.app_context():
        seed_roles_permissions_v2()


if __name__ == "__main__":
    main()
