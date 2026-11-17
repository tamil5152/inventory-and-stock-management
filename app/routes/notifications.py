from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.alerts import Notification

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("/")
@login_required
def list_notifications():

    limit = min(request.args.get("limit", 20, type=int) or 20, 100)
    since_id = request.args.get("since", 0, type=int)

    base = Notification.query.filter_by(user_id=current_user.id)
    unread = base.filter_by(is_read=False).count()
    items = base.order_by(Notification.id.desc()).limit(limit).all()
    new_items = [n for n in items if n.id > since_id] if since_id else []

    return jsonify({
        "success": True,
        "unread": unread,
        "data": [n.to_dict() for n in items],
        "new": [n.to_dict() for n in new_items if not n.is_read],
        "latest_id": items[0].id if items else 0,
    })


@notifications_bp.post("/<int:notification_id>/read")
@login_required
def mark_read(notification_id):

    notification = db.session.get(Notification, notification_id)

    if not notification or notification.user_id != current_user.id:
        return jsonify({"error": "Notification not found."}), 404

    notification.is_read = True
    db.session.commit()

    return jsonify({"success": True})


@notifications_bp.post("/read-all")
@login_required
def mark_all_read():

    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()

    return jsonify({"success": True})
