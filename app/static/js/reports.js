/* Reports page */

(() => {

    const e = StockFlow.escapeHtml;
    const loaded = {};

    const empty = (cols, text = "No data.") => `<tr><td colspan="${cols}" class="empty-state">${text}</td></tr>`;

    const loaders = {

        async stock() {

            const [categories, stock] = await Promise.all([
                StockFlow.api("/api/reports/categories"),
                StockFlow.api("/api/reports/stock"),
            ]);

            const totalUnits = categories.data.reduce((a, c) => a + c.units, 0);
            const totalValue = categories.data.reduce((a, c) => a + c.value, 0);

            document.getElementById("category-body").innerHTML = categories.data.length
                ? categories.data.map((c) => `
                    <tr><td>${e(c.category)}</td><td class="num">${c.products}</td>
                    <td class="num">${c.units}</td><td class="num">${StockFlow.money(c.value)}</td></tr>`).join("")
                  + `<tr class="total-row"><td>Total</td><td class="num">${stock.data.length}</td>
                    <td class="num">${totalUnits}</td><td class="num">${StockFlow.money(totalValue)}</td></tr>`
                : empty(4);

            document.getElementById("stock-body").innerHTML = stock.data.length
                ? stock.data.map((r) => `
                    <tr><td>${e(r.sku)}</td><td>${e(r.name)}</td><td>${e(r.category)}</td><td>${e(r.supplier || "-")}</td>
                    <td class="num">${r.quantity}</td><td class="num">${StockFlow.money(r.unit_price)}</td>
                    <td class="num">${StockFlow.money(r.stock_value)}</td><td>${StockFlow.badge(r.stock_status)}</td></tr>`).join("")
                : empty(8);
        },

        async movements() {

            const params = new URLSearchParams(new FormData(document.getElementById("movement-filter")));
            [...params.keys()].forEach((k) => { if (!params.get(k)) params.delete(k); });

            document.getElementById("movement-csv").href = `/api/reports/export/movements.csv?${params}`;

            const result = await StockFlow.api(`/api/reports/movements?${params}`);

            document.getElementById("movement-body").innerHTML = result.data.length
                ? result.data.map((m) => `
                    <tr><td>${StockFlow.formatDate(m.created_at)}</td>
                    <td><strong>${e(m.product_name)}</strong><br><small class="muted">${e(m.sku)}</small></td>
                    <td>${StockFlow.badge(m.movement_type)}</td><td class="num">${m.quantity}</td>
                    <td class="num">${m.previous_quantity}</td><td class="num">${m.new_quantity}</td>
                    <td>${e(m.reference_number || "-")}</td><td>${e(m.username || "-")}</td></tr>`).join("")
                : empty(8, "No movements in this range.");
        },

        async discrepancies() {

            const result = await StockFlow.api("/api/reports/discrepancies");

            document.getElementById("discrepancy-body").innerHTML = result.data.length
                ? result.data.map((s) => `
                    <tr><td>${StockFlow.formatDate(s.created_at)}</td><td><code>${e(s.barcode)}</code></td>
                    <td>${e(s.product_name || "-")}</td><td class="num">${s.expected_quantity ?? "-"}</td>
                    <td class="num">${s.physical_quantity}</td><td class="num">${s.discrepancy ?? "-"}</td>
                    <td>${StockFlow.badge(s.status)}</td>
                    <td>${s.risk_level ? StockFlow.badge(s.risk_level, Math.round(s.risk_score)) : "-"}</td>
                    <td>${e(s.username || "-")}</td></tr>`).join("")
                : empty(9, "No discrepancies recorded.");
        },

        async risk() {

            const result = await StockFlow.api("/api/reports/risk");

            document.getElementById("risk-body").innerHTML = result.data.length
                ? result.data.map((p, i) => `
                    <tr><td>${i + 1}</td><td><strong>${e(p.name)}</strong><br><small class="muted">${e(p.sku)}</small></td>
                    <td class="num">${p.quantity}</td><td class="num">${p.reorder_level}</td>
                    <td>${p.last_scan_status ? StockFlow.badge(p.last_scan_status) : "-"}</td>
                    <td>${StockFlow.badge(p.risk_level, Math.round(p.risk_score))}</td></tr>`).join("")
                : empty(6, "No risky products.");
        },

        async audit() {

            const result = await StockFlow.api("/api/reports/audit?limit=300");

            document.getElementById("audit-body").innerHTML = result.data.length
                ? result.data.map((a) => `
                    <tr><td>${StockFlow.formatDate(a.created_at)}</td><td>${e(a.username || "-")}</td>
                    <td><span class="badge badge-blue">${e(a.action)}</span></td>
                    <td>${e(a.entity_type)}${a.entity_id ? " #" + a.entity_id : ""}</td>
                    <td>${e(a.details || "")}</td><td>${e(a.ip_address || "-")}</td></tr>`).join("")
                : empty(6);
        },
    };

    async function show(tab, force = false) {

        document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
        document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.dataset.panel !== tab; });

        if (loaded[tab] && !force) return;

        try {
            await loaders[tab]();
            loaded[tab] = true;
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    }

    document.getElementById("report-tabs").addEventListener("click", (event) => {
        const tab = event.target.closest(".tab");
        if (tab) show(tab.dataset.tab);
    });

    document.getElementById("movement-filter").addEventListener("submit", (event) => {
        event.preventDefault();
        show("movements", true);
    });

    show("stock");
})();
