from app.extensions import db
from app.models import Role, Permission, RolePermission


def seed_roles_permissions():
    print("🌱 Seeding roles & permissions (safe/idempotent)...")

    # ---------- Roles ----------
    def get_or_create_role(name: str) -> Role:
        role = Role.query.filter_by(name=name).first()
        if role:
            return role
        role = Role(name=name)
        db.session.add(role)
        db.session.commit()
        return role

    admin_role = get_or_create_role("ADMIN")
    user_role = get_or_create_role("USER")

    # ---------- Permissions ----------
    permissions_data = [
        ("KB_MANAGE", "Manage knowledge base"),
        ("DIAGNOSIS_START", "Start diagnosis"),
        ("DIAGNOSIS_ANSWER", "Answer symptom questions"),
        ("DIAGNOSIS_VIEW", "View diagnosis result"),
        ("DIAGNOSIS_HISTORY", "View diagnosis history"),
    ]

    permissions = []
    for code, desc in permissions_data:
        p = Permission.query.filter_by(code=code).first()
        if not p:
            p = Permission(code=code, description=desc)
            db.session.add(p)
            db.session.commit()
        permissions.append(p)

    # ---------- Role-Permission Mapping ----------
    def link(role_id: int, perm_id: int):
        exists = RolePermission.query.filter_by(role_id=role_id, permission_id=perm_id).first()
        if not exists:
            db.session.add(RolePermission(role_id=role_id, permission_id=perm_id))
            db.session.commit()

    # ADMIN: all
    for p in permissions:
        link(admin_role.id, p.id)

    # USER: all except KB_MANAGE
    for p in permissions:
        if p.code != "KB_MANAGE":
            link(user_role.id, p.id)

    print("✅ RBAC seed done.")
