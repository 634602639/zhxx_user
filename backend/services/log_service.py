from models import db, OperationLog


def log_op(module: str, action: str, detail: str = "", success: bool = True):
    try:
        rec = OperationLog(module=module, action=action, detail=detail, success=success)
        db.session.add(rec)
        db.session.commit()
    except Exception:
        db.session.rollback()
