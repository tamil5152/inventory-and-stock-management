/* Products page */

(() => {

    const body = document.getElementById("products-body");
    const search = document.getElementById("product-search");
    const categoryFilter = document.getElementById("category-filter");
    const statusFilter = document.getElementById("status-filter");
    const archivedToggle = document.getElementById("archived-toggle");
    const form = document.getElementById("product-form");
    const canManage = StockFlow.hasRole("admin", "manager");
    const isAdmin = StockFlow.hasRole("admin");

    let products = [];
    let suppliersLoaded = false;

    const COMPUTER_ACCESSORY_CATEGORIES = [
        "Keyboards & Mice", "Monitors", "Cables & Adapters", "Storage", "Audio",
        "Networking", "Power & Charging", "Laptop Accessories", "Webcams", "Printers & Ink",
    ];

    async function loadProducts() {

        const params = new URLSearchParams();
        if (search.value.trim()) params.set("q", search.value.trim());
        if (categoryFilter.value) params.set("category", categoryFilter.value);
        if (statusFilter.value) params.set("status", statusFilter.value);
        if (archivedToggle?.checked) params.set("archived", "1");

        try {
            const result = await StockFlow.api(`/api/products/?${params}`);
            products = result.data;
            renderCategories(result.categories);
            render();
        } catch (error) {
            body.innerHTML = `<tr><td colspan="8" class="empty-state">${StockFlow.escapeHtml(error.message)}</td></tr>`;
        }
    }

    function renderCategories(categories) {

        const current = categoryFilter.value;
        categoryFilter.innerHTML = '<option value="">All categories</option>' +
            categories.map((c) => `<option ${c === current ? "selected" : ""}>${StockFlow.escapeHtml(c)}</option>`).join("");

        const suggestions = [...new Set([...COMPUTER_ACCESSORY_CATEGORIES, ...categories])];
        document.getElementById("category-list").innerHTML =
            suggestions.map((c) => `<option value="${StockFlow.escapeHtml(c)}">`).join("");
    }

    function render() {

        if (!products.length) {
            body.innerHTML = '<tr><td colspan="8" class="empty-state">No products found.</td></tr>';
            return;
        }

        const e = StockFlow.escapeHtml;

        body.innerHTML = products.map((p) => `
            <tr class="${p.is_active ? "" : "archived-row"}">
                <td><strong>${e(p.name)}</strong><br><small class="muted">${e(p.sku)}</small></td>
                <td><code>${e(p.barcode)}</code><br><small class="muted">count every ${p.count_interval_days} d</small></td>
                <td>${e(p.category)}</td>
                <td>${p.shelf_code ? `<span class="chip" title="${e(p.shelf_name)}">${e(p.shelf_code)}</span>` : '<span class="muted">-</span>'}</td>
                <td class="num">${StockFlow.money(p.unit_price)}</td>
                <td class="num"><strong>${p.quantity}</strong><br><small class="muted">reorder ≤ ${p.reorder_level}</small></td>
                <td>${p.is_active ? StockFlow.badge(p.stock_status) : '<span class="badge">Archived</span>'}</td>
                <td class="actions">
                    ${p.is_active ? `<button class="small-button" data-action="stock" data-id="${p.id}">Stock</button>` : ""}
                    ${canManage && p.is_active ? `<button class="small-button" data-action="edit" data-id="${p.id}">Edit</button>` : ""}
                    ${canManage && p.is_active ? `<button class="small-button danger" data-action="archive" data-id="${p.id}">Archive</button>` : ""}
                    ${canManage && !p.is_active ? `<button class="small-button" data-action="restore" data-id="${p.id}">Restore</button>` : ""}
                    ${isAdmin && !p.is_active ? `<button class="small-button danger" data-action="delete" data-id="${p.id}">Delete</button>` : ""}
                </td>
            </tr>`).join("");
    }

    async function loadSuppliers() {

        if (suppliersLoaded) return;

        try {
            const [result, shelves] = await Promise.all([StockFlow.api("/api/suppliers/"), StockFlow.api("/api/shelves/")]);
            document.getElementById("supplier-select").innerHTML =
                '<option value="">No supplier</option>' +
                result.data.map((s) => `<option value="${s.id}">${StockFlow.escapeHtml(s.company_name)}</option>`).join("");
            document.getElementById("shelf-select").innerHTML =
                '<option value="">Not on a shelf</option>' +
                shelves.data.map((s) => `<option value="${s.id}">${StockFlow.escapeHtml(s.code + " " + s.name)}${s.staff.length ? "" : " (nobody assigned)"}</option>`).join("");
            suppliersLoaded = true;
        } catch (_) { /* lists are optional */ }
    }

    async function openForm(product = null) {

        await loadSuppliers();
        form.reset();

        document.getElementById("product-modal-title").textContent = product ? "Edit product" : "Add product";
        document.getElementById("opening-qty-field").style.display = product ? "none" : "";
        form.sku.disabled = Boolean(product);

        if (product) {
            form.id.value = product.id;
            form.sku.value = product.sku;
            form.barcode.value = product.barcode;
            form.name.value = product.name;
            form.category.value = product.category;
            form.supplier_id.value = product.supplier_id || "";
            form.shelf_id.value = product.shelf_id || "";
            form.unit_price.value = product.unit_price;
            form.reorder_level.value = product.reorder_level;
            form.count_interval_days.value = product.count_interval_days || 30;
            form.description.value = product.description || "";
        } else {
            form.id.value = "";
        }

        StockFlow.openModal("product-modal");
    }

    form?.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const id = data.id;
        delete data.id;

        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;

        try {
            if (id) {
                delete data.sku;
                delete data.quantity;
                await StockFlow.api(`/api/products/${id}`, { method: "PUT", body: data });
                StockFlow.toast("Product updated.");
            } else {
                await StockFlow.api("/api/products/", { method: "POST", body: data });
                StockFlow.toast("Product created.");
            }

            StockFlow.closeModal("product-modal");
            loadProducts();

        } catch (error) {
            StockFlow.toast(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    body.addEventListener("click", async (event) => {

        const button = event.target.closest("button[data-action]");
        if (!button) return;

        const product = products.find((p) => p.id === Number(button.dataset.id));
        if (!product) return;

        const action = button.dataset.action;

        if (action === "stock") return StockModal.open(product, loadProducts);
        if (action === "edit") return openForm(product);

        const confirmText = {
            archive: `Archive "${product.name}"? It will be hidden from scanning and reports.`,
            restore: `Restore "${product.name}"?`,
            delete: `Permanently delete "${product.name}"? This cannot be undone.`,
        }[action];

        if (!confirm(confirmText)) return;

        try {
            if (action === "delete") {
                await StockFlow.api(`/api/products/${product.id}`, { method: "DELETE" });
            } else {
                await StockFlow.api(`/api/products/${product.id}/${action}`, { method: "POST" });
            }

            StockFlow.toast(`Product ${action}d.`);
            loadProducts();

        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    document.getElementById("add-product-btn")?.addEventListener("click", () => openForm());
    search.addEventListener("input", StockFlow.debounce(loadProducts));
    categoryFilter.addEventListener("change", loadProducts);
    statusFilter.addEventListener("change", loadProducts);
    archivedToggle?.addEventListener("change", loadProducts);

    const initialQuery = new URLSearchParams(window.location.search).get("q");
    if (initialQuery) search.value = initialQuery;

    loadProducts();
})();
