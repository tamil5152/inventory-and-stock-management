/* Shelves page */

(() => {

    const e = StockFlow.escapeHtml;
    const grid = document.getElementById("shelf-grid");
    const form = document.getElementById("shelf-form");
    const canManage = StockFlow.hasRole("admin", "manager");
    let shelves = [];
    let people = [];

    async function load() {

        try {
            shelves = (await StockFlow.api(`/api/shelves/${canManage ? "?inactive=1" : ""}`)).data;
        } catch (error) {
            grid.innerHTML = `<p class="muted">${e(error.message)}</p>`;
            return;
        }

        if (!shelves.length) {
            grid.innerHTML = `<div class="panel empty-state">No shelves yet.${canManage ? " Add your first shelf, then assign staff to it." : ""}</div>`;
            return;
        }

        grid.innerHTML = shelves.map((s) => `
            <article class="shelf-card ${s.is_active ? "" : "inactive"}">
                <div class="shelf-code">${e(s.code)}</div>
                <div class="shelf-body">
                    <h3>${e(s.name)}</h3>
                    <p class="muted">${e(s.location || "No location set")}</p>
                    <div class="shelf-facts">
                        <span><strong>${s.product_count}</strong> product${s.product_count === 1 ? "" : "s"}</span>
                        <span>${s.staff.length
                            ? e(s.staff.map((p) => p.name).join(", "))
                            : '<span class="text-red">Nobody assigned</span>'}</span>
                    </div>
                    ${!s.is_active ? '<span class="badge plain">Inactive</span>' : ""}
                </div>
                ${canManage ? `<div class="shelf-actions">
                    <button class="small-button" data-action="edit" data-id="${s.id}">Edit</button>
                    <button class="small-button ${s.is_active ? "danger" : ""}" data-action="toggle" data-id="${s.id}">${s.is_active ? "Deactivate" : "Activate"}</button>
                </div>` : ""}
            </article>`).join("");
    }

    async function openForm(shelf = null) {

        if (!people.length) {
            try {
                people = (await StockFlow.api("/api/checks/assignees")).data;
            } catch (error) {
                return StockFlow.toast(error.message, "error");
            }
        }

        form.reset();
        form.id.value = shelf?.id || "";
        document.getElementById("shelf-modal-title").textContent = shelf ? `Edit shelf ${shelf.code}` : "Add shelf";
        document.getElementById("shelf-submit").textContent = shelf ? "Save changes" : "Add shelf";

        if (shelf) {
            form.code.value = shelf.code;
            form.name.value = shelf.name;
            form.location.value = shelf.location || "";
        }

        const selected = shelf ? shelf.staff.map((p) => p.id) : [];
        document.getElementById("staff-options").innerHTML = people.map((p) => `
            <label class="check-tile">
                <input type="checkbox" name="staff_ids" value="${p.id}" ${selected.includes(p.id) ? "checked" : ""}>
                <span><strong>${e(p.name)}</strong> <small class="muted">${e(p.role)}${p.shelves.length ? ", shelves " + e(p.shelves.join(", ")) : ""}</small></span>
            </label>`).join("");

        StockFlow.openModal("shelf-modal");
    }

    form?.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const staffIds = [...form.querySelectorAll('input[name="staff_ids"]:checked')].map((i) => Number(i.value));
        const payload = { code: data.code, name: data.name, location: data.location, staff_ids: staffIds };

        try {
            if (data.id) {
                await StockFlow.api(`/api/shelves/${data.id}`, { method: "PUT", body: payload });
                StockFlow.toast(`Shelf ${data.code.toUpperCase()} saved. Newly assigned staff have been notified.`);
            } else {
                await StockFlow.api("/api/shelves/", { method: "POST", body: payload });
                StockFlow.toast(`Shelf ${data.code.toUpperCase()} added.`);
            }
            StockFlow.closeModal("shelf-modal");
            people = [];
            load();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    grid.addEventListener("click", async (event) => {

        const button = event.target.closest("button[data-action]");
        if (!button) return;

        const shelf = shelves.find((s) => s.id === Number(button.dataset.id));

        if (button.dataset.action === "edit") return openForm(shelf);

        try {
            await StockFlow.api(`/api/shelves/${shelf.id}/toggle`, { method: "POST" });
            StockFlow.toast(shelf.is_active ? `Shelf ${shelf.code} deactivated.` : `Shelf ${shelf.code} activated.`);
            load();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    document.getElementById("add-shelf-btn")?.addEventListener("click", () => openForm());

    load();
})();
