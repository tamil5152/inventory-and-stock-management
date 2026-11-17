/* Barcode scanner / stock verification page */

(() => {

    const e = StockFlow.escapeHtml;
    const lookupForm = document.getElementById("lookup-form");
    const barcodeInput = document.getElementById("barcode-input");
    const productCard = document.getElementById("product-card");
    const verifyForm = document.getElementById("verify-form");
    const physicalInput = document.getElementById("physical-input");
    const resultBox = document.getElementById("result-box");
    const sessionBadge = document.getElementById("session-count");
    const canAdjust = StockFlow.hasRole("admin", "manager");

    let currentBarcode = null;
    let currentProduct = null;

    function setSessionCount(count) {
        sessionBadge.textContent = `${count || 0} counted this session`;
    }

    function clearScan() {

        currentBarcode = null;
        currentProduct = null;
        productCard.hidden = true;
        verifyForm.hidden = true;
        lookupForm.reset();
        barcodeInput.focus();
    }

    async function lookup(barcode) {

        barcode = barcode.trim();
        if (!barcode) return;

        currentBarcode = barcode;
        productCard.hidden = false;
        productCard.innerHTML = '<p class="muted">Looking up…</p>';

        try {
            const result = await StockFlow.api(`/api/scanning/lookup/${encodeURIComponent(barcode)}`);
            const p = result.data;
            currentProduct = p;

            productCard.className = "product-card";
            productCard.innerHTML = `
                <div class="row-between">
                    <div>
                        <h3>${e(p.name)}</h3>
                        <p class="muted">${e(p.sku)}, ${e(p.category)}, <code>${e(p.barcode)}</code></p>
                    </div>
                    ${result.already_scanned ? '<span class="badge badge-amber">Already scanned this session</span>' : ""}
                </div>
                <p class="muted" style="margin-top:8px">System quantity is hidden until you submit the count (blind count).</p>`;

        } catch (error) {
            currentProduct = null;
            productCard.className = "product-card warning";
            productCard.innerHTML = `
                <h3>Unknown barcode</h3>
                <p class="muted"><code>${e(barcode)}</code> is not linked to an active product.
                You can still record the count — it will be logged as UNKNOWN_BARCODE for review.</p>`;
        }

        verifyForm.hidden = false;
        verifyForm.reset();
        physicalInput.focus();
    }

    async function verify(force = false) {

        const quantity = physicalInput.value.trim();

        if (quantity === "" || Number(quantity) < 0) {
            StockFlow.toast("Enter the counted quantity.", "warning");
            return physicalInput.focus();
        }

        try {
            const result = await StockFlow.api("/api/scanning/verify", {
                method: "POST",
                body: { barcode: currentBarcode, physical_quantity: Number(quantity), force },
            });

            renderResult(result);
            setSessionCount(result.session_count);

            if (result.completed_checks) {
                StockFlow.toast(`Stock check completed for ${result.product.name}.`);
                document.getElementById("task-context").hidden = true;
                window.StockFlowAlerts?.refresh();
            }
            loadHistory();

            const savedProduct = currentProduct;
            clearScan();
            currentProduct = savedProduct;

        } catch (error) {

            if (error.status === 409 && error.data?.status === "DUPLICATE") {
                if (confirm("This barcode was already verified in this session. Record another count anyway?")) {
                    return verify(true);
                }
                return;
            }

            StockFlow.toast(error.message, "error");
        }
    }

    function renderResult(result) {

        if (result.status === "UNKNOWN_BARCODE") {
            resultBox.className = "result-box";
            resultBox.innerHTML = `
                <div class="result-header">${StockFlow.badge("UNKNOWN_BARCODE")}</div>
                <p>Barcode <code>${e(result.verification.barcode)}</code> was logged for review with
                a physical count of <strong>${result.verification.physical_quantity}</strong>.</p>`;
            return;
        }

        const risk = result.risk;
        const diff = result.discrepancy;
        const diffText = diff === 0 ? "0" : (diff > 0 ? `+${diff} (surplus)` : `${diff} (shortage)`);

        resultBox.className = "result-box";
        resultBox.innerHTML = `
            <div class="result-header">
                <div>
                    <h3>${e(result.product.name)}</h3>
                    <p class="muted">${e(result.product.sku)}</p>
                </div>
                ${StockFlow.badge(result.status)}
            </div>

            <div class="result-stats">
                <div><span>Expected (system)</span><strong>${result.expected_quantity}</strong></div>
                <div><span>Counted</span><strong>${result.physical_quantity}</strong></div>
                <div><span>Difference</span><strong class="${diff === 0 ? "text-green" : "text-red"}">${diffText}</strong></div>
            </div>

            <div class="risk-meter">
                <div class="risk-bar risk-bg-${risk.level.toLowerCase()}" style="width:${risk.score}%"></div>
            </div>
            <p>Risk: ${StockFlow.badge(risk.level, risk.score)}</p>

            <ul class="factor-list">
                <li>Discrepancy factor: <strong>${risk.factors.discrepancy}</strong> / 50</li>
                <li>Low stock factor: <strong>${risk.factors.low_stock}</strong> / 30</li>
                <li>Unexpected stock factor: <strong>${risk.factors.unexpected_stock}</strong> / 20</li>
            </ul>

            ${result.status === "DISCREPANCY" && canAdjust ? `
                <button class="primary-button" id="apply-count"
                        data-product="${result.product.id}" data-qty="${result.physical_quantity}">
                    Apply counted quantity (${result.physical_quantity}) to stock
                </button>` : ""}
            ${result.status === "DISCREPANCY" && !canAdjust ? `
                <p class="muted">Ask a manager to review and adjust this discrepancy.</p>` : ""}`;
    }

    resultBox.addEventListener("click", async (event) => {

        const button = event.target.closest("#apply-count");
        if (!button) return;

        if (!confirm(`Set system stock to ${button.dataset.qty}?`)) return;

        try {
            const result = await StockFlow.api("/api/inventory/adjust", {
                method: "POST",
                body: {
                    product_id: Number(button.dataset.product),
                    quantity: Number(button.dataset.qty),
                    notes: "Adjusted after barcode stock verification",
                },
            });

            StockFlow.toast(`Stock adjusted: ${result.previous_quantity} → ${result.new_quantity}`);
            button.replaceWith(Object.assign(document.createElement("p"), {
                className: "text-green", textContent: "✓ Stock adjusted to the counted quantity.",
            }));

        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    async function loadHistory() {

        const body = document.getElementById("scan-history");
        const issues = document.getElementById("issues-only").checked ? "&issues=1" : "";

        try {
            const result = await StockFlow.api(`/api/scanning/history?limit=50${issues}`);
            setSessionCount(result.session_count);

            body.innerHTML = result.data.length ? result.data.map((s) => `
                <tr>
                    <td>${StockFlow.formatDate(s.created_at)}</td>
                    <td><code>${e(s.barcode)}</code></td>
                    <td>${e(s.product_name || "-")}</td>
                    <td class="num">${s.expected_quantity ?? "-"}</td>
                    <td class="num">${s.physical_quantity}</td>
                    <td class="num">${s.discrepancy ?? "-"}</td>
                    <td>${StockFlow.badge(s.status)}</td>
                    <td>${s.risk_level ? StockFlow.badge(s.risk_level, Math.round(s.risk_score)) : "-"}</td>
                    <td>${e(s.username || "-")}</td>
                </tr>`).join("")
                : '<tr><td colspan="9" class="empty-state">No scans recorded yet.</td></tr>';

        } catch (error) {
            body.innerHTML = `<tr><td colspan="9" class="empty-state">${e(error.message)}</td></tr>`;
        }
    }

    // ---------------- Camera scanning (BarcodeDetector API) ----------------

    let stream = null;
    let scanning = false;

    async function startCamera() {

        if (!("BarcodeDetector" in window)) {
            StockFlow.toast("Camera scanning needs Chrome/Edge on Android or desktop with BarcodeDetector support. Use a USB scanner or type the code.", "warning");
            return;
        }

        const box = document.getElementById("camera-box");
        const video = document.getElementById("camera-video");
        const status = document.getElementById("camera-status");

        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        } catch (error) {
            StockFlow.toast("Camera permission denied or not available.", "error");
            return;
        }

        const detector = new BarcodeDetector({
            formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "qr_code"],
        });

        video.srcObject = stream;
        await video.play();
        box.hidden = false;
        scanning = true;

        const tick = async () => {

            if (!scanning) return;

            try {
                const codes = await detector.detect(video);

                if (codes.length) {
                    const value = codes[0].rawValue;
                    status.textContent = `Detected: ${value}`;
                    stopCamera();
                    barcodeInput.value = value;
                    return lookup(value);
                }
            } catch (_) { /* frame not ready */ }

            requestAnimationFrame(tick);
        };

        tick();
    }

    function stopCamera() {

        scanning = false;
        stream?.getTracks().forEach((t) => t.stop());
        stream = null;
        document.getElementById("camera-box").hidden = true;
    }

    // ---------------- Wiring ----------------

    lookupForm.addEventListener("submit", (event) => {
        event.preventDefault();
        lookup(barcodeInput.value);
    });

    verifyForm.addEventListener("submit", (event) => {
        event.preventDefault();
        verify(false);
    });

    document.getElementById("clear-scan").addEventListener("click", clearScan);
    document.getElementById("camera-btn").addEventListener("click", startCamera);
    document.getElementById("camera-stop").addEventListener("click", stopCamera);
    document.getElementById("issues-only").addEventListener("change", loadHistory);

    document.getElementById("reset-session").addEventListener("click", async () => {

        try {
            await StockFlow.api("/api/scanning/session/reset", { method: "POST" });
            setSessionCount(0);
            StockFlow.toast("New scan session started.");
            clearScan();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    // Opened from a stock check or notification: /scanner?barcode=...&task=...
    const params = new URLSearchParams(window.location.search);
    const presetBarcode = params.get("barcode");

    if (params.get("task")) {
        StockFlow.api(`/api/checks/${Number(params.get("task"))}/start`, { method: "POST" })
            .then((result) => {
                const t = result.data;
                document.getElementById("task-context-text").textContent =
                    `Stock check for ${t.product_name}: ${t.reason_text.toLowerCase()}. Recording the count completes it.`;
                document.getElementById("task-context").hidden = false;
            })
            .catch(() => { /* check already closed or not yours; scanning still works */ });
    }

    if (presetBarcode) {
        barcodeInput.value = presetBarcode;
        lookup(presetBarcode);
    }

    loadHistory();
})();
