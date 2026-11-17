import csv
import io
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, Response, send_file
from flask_login import login_required

from app.models.audit import AuditLog
from app.services.report_service import ReportService
from app.services.priority_service import PriorityService
from app.utils.decorators import role_required
from app.utils.dsa import merge_sort

reports_bp = Blueprint("reports", __name__)


def _parse_date(value, end=False):

    if not value:
        return None

    try:
        date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("Dates must use YYYY-MM-DD format.")

    return date + timedelta(days=1) if end else date


def _movement_filters():

    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"), end=True)
    movement_type = request.args.get("type", "").upper() or None

    if movement_type and movement_type not in ("STOCK_IN", "STOCK_OUT", "ADJUSTMENT"):
        raise ValueError("Invalid movement type.")

    return start, end, movement_type


@reports_bp.get("/summary")
@login_required
def summary():
    return jsonify({"success": True, "data": ReportService.get_dashboard_summary()})


@reports_bp.get("/stock")
@login_required
def stock():
    return jsonify({"success": True, "data": ReportService.get_stock_report()})


@reports_bp.get("/categories")
@login_required
def categories():
    return jsonify({"success": True, "data": ReportService.get_category_summary()})


@reports_bp.get("/movements")
@login_required
def movements():

    try:
        start, end, movement_type = _movement_filters()
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify({
        "success": True,
        "data": ReportService.get_movement_report(start, end, movement_type),
    })


@reports_bp.get("/discrepancies")
@login_required
def discrepancies():
    return jsonify({"success": True, "data": ReportService.get_discrepancy_report()})


@reports_bp.get("/risk")
@login_required
def risk():
    """Risk ranking sorted with merge sort (highest risk first)."""

    data = merge_sort(PriorityService.get_prioritized_products(), key="risk_score")

    return jsonify({"success": True, "data": data})


@reports_bp.get("/audit")
@login_required
@role_required("admin")
def audit():

    limit = min(request.args.get("limit", 200, type=int) or 200, 1000)
    rows = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return jsonify({"success": True, "data": [row.to_dict() for row in rows]})


# ---------------------------------------------------------------
# Exports
# ---------------------------------------------------------------

def _csv_response(filename, headers, rows):

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)

    for row in rows:
        # Neutralise spreadsheet formula injection.
        writer.writerow([
            f"'{cell}" if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@") else cell
            for cell in row
        ])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@reports_bp.get("/export/stock.csv")
@login_required
def export_stock_csv():

    rows = ReportService.get_stock_report()

    return _csv_response(
        "stock_report.csv",
        ["SKU", "Barcode", "Name", "Category", "Supplier", "Quantity",
         "Reorder Level", "Unit Price", "Stock Value", "Status"],
        [
            [r["sku"], r["barcode"], r["name"], r["category"], r["supplier"],
             r["quantity"], r["reorder_level"], f'{r["unit_price"]:.2f}',
             f'{r["stock_value"]:.2f}', r["stock_status"]]
            for r in rows
        ],
    )


@reports_bp.get("/export/movements.csv")
@login_required
def export_movements_csv():

    try:
        start, end, movement_type = _movement_filters()
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    rows = ReportService.get_movement_report(start, end, movement_type, limit=10000)

    return _csv_response(
        "stock_movements.csv",
        ["Date", "SKU", "Product", "Type", "Quantity", "Previous",
         "New", "User", "Reference", "Notes"],
        [
            [r["created_at"], r["sku"], r["product_name"], r["movement_type"],
             r["quantity"], r["previous_quantity"], r["new_quantity"],
             r["username"] or "", r["reference_number"] or "", r["notes"] or ""]
            for r in rows
        ],
    )


@reports_bp.get("/export/stock.pdf")
@login_required
def export_stock_pdf():

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )

    rows = ReportService.get_stock_report()
    summary = ReportService.get_dashboard_summary()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28,
    )
    styles = getSampleStyleSheet()

    story = [
        Paragraph("StockFlow - Stock Report", styles["Title"]),
        Paragraph(
            datetime.now().strftime("Generated on %d %b %Y, %H:%M"),
            styles["Normal"],
        ),
        Spacer(1, 10),
        Paragraph(
            f"Products: {summary['total_products']} &nbsp;&nbsp; "
            f"Units: {summary['total_units']} &nbsp;&nbsp; "
            f"Low stock: {summary['low_stock_count']} &nbsp;&nbsp; "
            f"Stock value: Rs. {summary['total_stock_value']:,.2f}",
            styles["Normal"],
        ),
        Spacer(1, 14),
    ]

    table_data = [["SKU", "Name", "Category", "Qty", "Reorder", "Unit Price", "Value", "Status"]]

    for r in rows:
        table_data.append([
            r["sku"], r["name"][:40], r["category"][:20], r["quantity"],
            r["reorder_level"], f'{r["unit_price"]:,.2f}',
            f'{r["stock_value"]:,.2f}', r["stock_status"].replace("_", " "),
        ])

    if len(table_data) == 1:
        table_data.append(["-", "No products", "", "", "", "", "", ""])

    table = Table(table_data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17223b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d5dbe6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fb")]),
        ("ALIGN", (3, 1), (6, -1), "RIGHT"),
    ]

    for index, r in enumerate(rows, start=1):
        if r["stock_status"] != "IN_STOCK":
            style.append(("TEXTCOLOR", (7, index), (7, index), colors.HexColor("#bd3636")))

    table.setStyle(TableStyle(style))
    story.append(table)
    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="stock_report.pdf",
    )
