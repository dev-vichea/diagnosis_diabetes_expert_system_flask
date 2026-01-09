from app.extensions import db
from app.models import Role, Permission, RolePermission


def seed_roles_permissions_v2():
    """
    RBAC V2:
      Roles: ADMIN, KB_DOCTOR, USER
      Permissions:
        - KB_* for knowledge base CRUD
        - CASE_* for viewing all assessments & facts
        - DIAGNOSIS_* for diagnosis flow
      Mapping:
        - ADMIN: all permissions
        - KB_DOCTOR: KB_* + CASE_* + DIAGNOSIS_VIEW/HISTORY
        - USER: DIAGNOSIS_* only
    """
    print("🌱 Seeding RBAC v2 (safe/idempotent)...")

    def get_or_create_role(name: str) -> Role:
        role = Role.query.filter_by(name=name).first()
        if role:
            return role
        role = Role(name=name)
        db.session.add(role)
        db.session.commit()
        return role

    def get_or_create_perm(code: str, desc: str) -> Permission:
        p = Permission.query.filter_by(code=code).first()
        if p:
            # keep description updated (optional)
            if (p.description or "") != desc:
                p.description = desc
                db.session.commit()
            return p
        p = Permission(code=code, description=desc)
        db.session.add(p)
        db.session.commit()
        return p

    def link(role: Role, perm: Permission):
        exists = RolePermission.query.filter_by(role_id=role.id, permission_id=perm.id).first()
        if not exists:
            db.session.add(RolePermission(role_id=role.id, permission_id=perm.id))
            db.session.commit()

    # ---- Roles ----
    admin = get_or_create_role("ADMIN")
    kb_doctor = get_or_create_role("KB_DOCTOR")
    user = get_or_create_role("USER")

    # ---- Permissions ----
    perms = {}

    # KB CRUD
    perms["KB_VIEW"] = get_or_create_perm("KB_VIEW", "View knowledge base")
    perms["KB_CREATE"] = get_or_create_perm("KB_CREATE", "Create knowledge base items")
    perms["KB_UPDATE"] = get_or_create_perm("KB_UPDATE", "Update knowledge base items")
    perms["KB_DELETE"] = get_or_create_perm("KB_DELETE", "Delete knowledge base items")

    # Case/facts view (doctor/admin)
    perms["CASE_VIEW_ALL"] = get_or_create_perm("CASE_VIEW_ALL", "View all assessments/results")
    perms["CASE_VIEW_FACTS"] = get_or_create_perm("CASE_VIEW_FACTS", "View assessment answers (facts)")

    # Diagnosis flow
    perms["DIAGNOSIS_START"] = get_or_create_perm("DIAGNOSIS_START", "Start diagnosis")
    perms["DIAGNOSIS_ANSWER"] = get_or_create_perm("DIAGNOSIS_ANSWER", "Answer symptom questions")
    perms["DIAGNOSIS_VIEW"] = get_or_create_perm("DIAGNOSIS_VIEW", "View diagnosis result/progress")
    perms["DIAGNOSIS_HISTORY"] = get_or_create_perm("DIAGNOSIS_HISTORY", "View diagnosis history")

    # ---- Mapping ----
    # ADMIN: everything
    for p in perms.values():
        link(admin, p)

    # KB_DOCTOR: KB CRUD + view all cases/facts + view history/results
    for code in ("KB_VIEW", "KB_CREATE", "KB_UPDATE", "KB_DELETE", "CASE_VIEW_ALL", "CASE_VIEW_FACTS", "DIAGNOSIS_VIEW", "DIAGNOSIS_HISTORY"):
        link(kb_doctor, perms[code])

    # USER: diagnosis only (start/answer/view/history)
    for code in ("DIAGNOSIS_START", "DIAGNOSIS_ANSWER", "DIAGNOSIS_VIEW", "DIAGNOSIS_HISTORY"):
        link(user, perms[code])

    print("✅ RBAC v2 seeded.")
