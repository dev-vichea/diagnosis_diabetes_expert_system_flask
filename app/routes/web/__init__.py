from flask import Blueprint

web_bp = Blueprint("web", __name__)

# Route modules register handlers on web_bp when imported.
from . import auth_routes  # noqa: F401
from . import dashboard_routes  # noqa: F401
from . import diagnosis_routes  # noqa: F401
from .admin import dashboard_routes as admin_dashboard_routes  # noqa: F401
from .admin import users_routes as admin_users_routes  # noqa: F401
from .admin import roles_routes as admin_roles_routes  # noqa: F401
from .admin import reports_routes as admin_reports_routes  # noqa: F401
from .kb import symptoms_routes as kb_symptoms_routes  # noqa: F401
from .kb import rules_routes as kb_rules_routes  # noqa: F401
from .kb import diseases_routes as kb_diseases_routes  # noqa: F401
