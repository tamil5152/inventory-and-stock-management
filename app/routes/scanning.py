from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user

from app.repositories.product_repository import ProductRepository
from app.repositories.scan_repository import ScanRepository
from app.services.verification_service import VerificationService
from app.utils.dsa import DuplicateScanDetector, ScanQueue
from app.utils.validators import validate_quantity

scanning_bp = Blueprint("scanning", __name__)

SESSION_KEY = "scan_session_barcodes"


def _detector():
    """Rebuild the per-user duplicate detector (HashSet) from the session."""

    detector = DuplicateScanDetector()

    for barcode in session.get(SESSION_KEY, []):
        detector.check_and_add(barcode)

    return detector


def _save_detector(detector):

    session[SESSION_KEY] = sorted(detector.scanned)


@scanning_bp.get("/lookup/<string:barcode>")
@login_required
def lookup(barcode):

    product = ProductRepository.get_by_barcode(barcode.strip())

    if not product or not product.is_active:
        return jsonify({
            "success": False,
            "error": "Unknown barcode.",
        }), 404

    return jsonify({
        "success": True,
        "data": product.to_dict(),
        "already_scanned": barcode.strip() in session.get(SESSION_KEY, []),
    })


@scanning_bp.post("/verify")
@login_required
def verify():

    data = request.get_json(silent=True) or {}
    barcode = str(data.get("barcode", "")).strip()
    force = bool(data.get("force"))

    try:
        physical_quantity = validate_quantity(data.get("physical_quantity"))
    except ValueError:
        return jsonify({"error": "Physical quantity must be a non-negative integer."}), 400

    if not barcode:
        return jsonify({"error": "Barcode is required."}), 400

    detector = _detector()

    if barcode in detector.scanned and not force:
        return jsonify({
            "success": False,
            "status": "DUPLICATE",
            "error": "This barcode was already verified in the current scan session.",
        }), 409

    try:
        result = VerificationService.verify(
            barcode, physical_quantity, current_user.id
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    detector.check_and_add(barcode)
    _save_detector(detector)
    result["session_count"] = detector.count()

    return jsonify(result)


@scanning_bp.post("/batch")
@login_required
def batch_verify():
    """Process several scans in FIFO order using the ScanQueue."""

    data = request.get_json(silent=True) or {}
    items = data.get("scans") or []

    if not isinstance(items, list) or not items:
        return jsonify({"error": "Provide a non-empty 'scans' list."}), 400

    if len(items) > 200:
        return jsonify({"error": "At most 200 scans per batch."}), 400

    queue = ScanQueue()

    for item in items:
        queue.enqueue(item)

    detector = _detector()
    results = []

    while not queue.is_empty():

        item = queue.dequeue() or {}
        barcode = str(item.get("barcode", "")).strip()

        if detector.check_and_add(barcode):
            results.append({"barcode": barcode, "status": "DUPLICATE"})
            continue

        try:
            result = VerificationService.verify(
                barcode, item.get("physical_quantity"), current_user.id
            )
            results.append({
                "barcode": barcode,
                "status": result["status"],
                "discrepancy": result.get("discrepancy"),
            })
        except ValueError as error:
            detector.remove(barcode)
            results.append({"barcode": barcode, "status": "ERROR", "error": str(error)})

    _save_detector(detector)

    return jsonify({"success": True, "data": results})


@scanning_bp.post("/session/reset")
@login_required
def reset_session():

    session.pop(SESSION_KEY, None)

    return jsonify({"success": True, "message": "Scan session cleared."})


@scanning_bp.get("/history")
@login_required
def history():

    limit = min(request.args.get("limit", 50, type=int) or 50, 500)
    only_issues = request.args.get("issues") == "1"

    rows = (
        ScanRepository.get_discrepancies(limit)
        if only_issues
        else ScanRepository.get_all(limit)
    )

    return jsonify({
        "success": True,
        "data": [row.to_dict() for row in rows],
        "session_count": len(session.get(SESSION_KEY, [])),
    })
