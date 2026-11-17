/* Shared stock movement modal. Call StockModal.open(product, onDone). */

const StockModal = (() => {

    const form = document.getElementById("stock-form");
    let onDone = null;

    const endpoints = {
        STOCK_IN: "/api/inventory/stock-in",
        STOCK_OUT: "/api/inventory/stock-out",
        ADJUSTMENT: "/api/inventory/adjust",
    };

    function updateLabel() {

        const type = form.querySelector('input[name="movement_type"]:checked')?.value;
        document.getElementById("stock-qty-label").textContent =
            type === "ADJUSTMENT" ? "Counted quantity *" : "Quantity *";
    }

    function open(product, callback, defaultType = "STOCK_IN") {

        onDone = callback;
        form.reset();
        form.product_id.value = product.id;

        const radio = form.querySelector(`input[name="movement_type"][value="${defaultType}"]`);
        if (radio) radio.checked = true;
        updateLabel();

        document.getElementById("stock-modal-product").innerHTML =
            `<strong>${StockFlow.escapeHtml(product.name)}</strong> (${StockFlow.escapeHtml(product.sku)}) — ` +
            `current stock: <strong>${product.quantity}</strong>`;

        StockFlow.openModal("stock-modal");
    }

    form?.addEventListener("change", (e) => {
        if (e.target.name === "movement_type") updateLabel();
    });

    form?.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;

        try {
            const result = await StockFlow.api(endpoints[data.movement_type], {
                method: "POST",
                body: {
                    product_id: Number(data.product_id),
                    quantity: Number(data.quantity),
                    notes: data.notes,
                    reference_number: data.reference_number,
                },
            });

            StockFlow.toast(
                `${result.product}: ${result.previous_quantity} → ${result.new_quantity}` +
                (result.low_stock ? " (low stock!)" : ""),
                result.low_stock ? "warning" : "success"
            );

            StockFlow.closeModal("stock-modal");
            if (onDone) onDone(result);

        } catch (error) {
            StockFlow.toast(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    return { open };
})();
