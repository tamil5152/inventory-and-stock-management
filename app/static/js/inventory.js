/* Inventory page */

(() => {

    const e = StockFlow.escapeHtml;
    const quickSelect = document.getElementById("quick-product");
    const historySelect = document.getElementById("history-product");
    let products = [];

    async function loadProducts() {

        const result = await StockFlow.api("/api/products/");
        products = result.data;

        const options = products.map((p) =>
            `<option value="${p.id}">${e(p.name)} — ${e(p.sku)} — ${e(p.barcode)} (qty ${p.quantity})</option>`
        ).join("");

        const selectedQuick = quickSelect.value;
        const selectedHistory = historySelect.value;

        quickSelect.innerHTML = '<option value="">Select a product…</option>' + options;
        historySelect.innerHTML = '<option value="">All products</option>' + products.map((p) =>
            `<option value="${p.id}">${e(p.name)} (${e(p.sku)})</option>`).join("");

        quickSelect.value = selectedQuick;
        historySelect.value = selectedHistory;
    }

    async function loadLowStock() {

        const body = document.getElementById("low-stock-body");
        const result = await StockFlow.api("/api/inventory/low-stock");

        body.innerHTML = result.data.length ? result.data.map((p) => `
            <tr>
                <td><strong>${e(p.name)}</strong><br><small class="muted">${e(p.sku)}</small></td>
                <td class="num">${StockFlow.badge(p.stock_status, p.quantity)}</td>
                <td class="num">${p.reorder_level}</td>
                <td class="actions"><button class="small-button" data-restock="${p.id}">Restock</button></td>
            </tr>`).join("")
            : '<tr><td colspan="4" class="empty-state">Every product is above its reorder level.</td></tr>';
    }

    async function loadHistory() {

        const body = document.getElementById("history-body");
        const params = new URLSearchParams({ limit: 200 });
        if (historySelect.value) params.set("product_id", historySelect.value);

        const result = await StockFlow.api(`/api/inventory/movements?${params}`);

        body.innerHTML = result.data.length ? result.data.map((m) => `
            <tr>
                <td>${StockFlow.formatDate(m.created_at)}</td>
                <td><strong>${e(m.product_name)}</strong><br><small class="muted">${e(m.sku)}</small></td>
                <td>${StockFlow.badge(m.movement_type)}</td>
                <td class="num">${m.quantity}</td>
                <td class="num">${m.previous_quantity}</td>
                <td class="num">${m.new_quantity}</td>
                <td>${e(m.reference_number || "-")}</td>
                <td>${e(m.notes || "-")}</td>
                <td>${e(m.username || "-")}</td>
            </tr>`).join("")
            : '<tr><td colspan="9" class="empty-state">No movements yet.</td></tr>';
    }

    async function refreshAll() {

        try {
            await loadProducts();
            await Promise.all([loadLowStock(), loadHistory()]);
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    }

    document.querySelectorAll("[data-quick]").forEach((button) => {

        button.addEventListener("click", () => {

            const product = products.find((p) => p.id === Number(quickSelect.value));

            if (!product) {
                StockFlow.toast("Select a product first.", "warning");
                return quickSelect.focus();
            }

            StockModal.open(product, refreshAll, button.dataset.quick);
        });
    });

    document.getElementById("low-stock-body").addEventListener("click", (event) => {

        const button = event.target.closest("[data-restock]");
        if (!button) return;

        const product = products.find((p) => p.id === Number(button.dataset.restock));
        if (product) StockModal.open(product, refreshAll, "STOCK_IN");
    });

    historySelect.addEventListener("change", loadHistory);

    refreshAll();
})();
