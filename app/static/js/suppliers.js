/* Suppliers page */

(() => {

    const e = StockFlow.escapeHtml;
    const body = document.getElementById("suppliers-body");
    const form = document.getElementById("supplier-form");
    const search = document.getElementById("supplier-search");
    const inactiveToggle = document.getElementById("inactive-toggle");
    const canManage = StockFlow.hasRole("admin", "manager");
    let suppliers = [];

    async function load() {

        try {
            const result = await StockFlow.api(`/api/suppliers/${inactiveToggle?.checked ? "?inactive=1" : ""}`);
            suppliers = result.data;
            render();
        } catch (error) {
            body.innerHTML = `<tr><td colspan="8" class="empty-state">${e(error.message)}</td></tr>`;
        }
    }

    function render() {

        const term = search.value.trim().toLowerCase();
        const rows = suppliers.filter((s) =>
            !term || [s.company_name, s.contact_person, s.email, s.phone].some((v) => (v || "").toLowerCase().includes(term)));

        body.innerHTML = rows.length ? rows.map((s) => `
            <tr class="${s.is_active ? "" : "archived-row"}">
                <td><strong>${e(s.company_name)}</strong><br><small class="muted">${e(s.address || "")}</small></td>
                <td>${e(s.contact_person || "-")}</td>
                <td>${e(s.phone)}</td>
                <td>${e(s.email || "-")}</td>
                <td>${e(s.tax_id || "-")}</td>
                <td class="num">${s.product_count}</td>
                <td>${s.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge">Inactive</span>'}</td>
                <td class="actions">
                    ${canManage ? `<button class="small-button" data-action="edit" data-id="${s.id}">Edit</button>
                    <button class="small-button ${s.is_active ? "danger" : ""}" data-action="toggle" data-id="${s.id}">${s.is_active ? "Deactivate" : "Activate"}</button>` : ""}
                </td>
            </tr>`).join("")
            : '<tr><td colspan="8" class="empty-state">No suppliers found.</td></tr>';
    }

    function openForm(supplier = null) {

        form.reset();
        document.getElementById("supplier-modal-title").textContent = supplier ? "Edit supplier" : "Add supplier";
        form.id.value = supplier?.id || "";

        if (supplier) {
            ["company_name", "contact_person", "phone", "email", "tax_id", "address"].forEach((f) => {
                form[f].value = supplier[f] || "";
            });
        }

        StockFlow.openModal("supplier-modal");
    }

    form?.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const id = data.id;
        delete data.id;

        try {
            if (id) {
                await StockFlow.api(`/api/suppliers/${id}`, { method: "PUT", body: data });
            } else {
                await StockFlow.api("/api/suppliers/", { method: "POST", body: data });
            }

            StockFlow.toast(id ? "Supplier updated." : "Supplier created.");
            StockFlow.closeModal("supplier-modal");
            load();

        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    body.addEventListener("click", async (event) => {

        const button = event.target.closest("button[data-action]");
        if (!button) return;

        const supplier = suppliers.find((s) => s.id === Number(button.dataset.id));

        if (button.dataset.action === "edit") return openForm(supplier);

        try {
            await StockFlow.api(`/api/suppliers/${supplier.id}/toggle`, { method: "POST" });
            StockFlow.toast("Supplier status changed.");
            load();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    document.getElementById("add-supplier-btn")?.addEventListener("click", () => openForm());
    search.addEventListener("input", render);
    inactiveToggle?.addEventListener("change", load);

    load();
})();
