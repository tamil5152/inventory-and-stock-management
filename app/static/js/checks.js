/* Stock checks page */

(() => {

    const e = StockFlow.escapeHtml;
    const listEl = document.getElementById("task-list");
    const summaryEl = document.getElementById("summary");
    const isManager = StockFlow.hasRole("admin", "manager");
    const form = document.getElementById("check-form");

    let status = "open";
    let tasks = [];
    let assigneesLoaded = false;

    function scope() {
        return document.querySelector('input[name="scope"]:checked')?.value || "mine";
    }

    function dueText(task) {

        if (!task.due_at) return "";
        const due = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(task.due_at) ? task.due_at : task.due_at + "Z");
        const hours = Math.round((due - Date.now()) / 3600000);

        if (task.is_overdue) return `<span class="overdue">Overdue by ${Math.max(1, -hours)} h</span>`;
        if (hours < 24) return `Due in ${Math.max(hours, 0)} h`;
        return `Due ${StockFlow.formatDate(task.due_at)}`;
    }

    function renderSummary(s) {

        summaryEl.innerHTML = `
            <span class="pill"><strong>${s.open}</strong> open</span>
            <span class="pill ${s.high ? "bad" : ""}"><strong>${s.high}</strong> high priority</span>
            <span class="pill ${s.overdue ? "warn" : ""}"><strong>${s.overdue}</strong> overdue</span>`;
    }

    function render() {

        if (!tasks.length) {
            listEl.innerHTML = status === "open"
                ? `<p class="empty-state">Nothing to count right now. New checks appear here automatically${isManager ? ", or use Request a count" : ""}.</p>`
                : '<p class="empty-state">No completed checks yet.</p>';
            return;
        }

        listEl.innerHTML = tasks.map((t) => {

            const open = t.status === "OPEN" || t.status === "IN_PROGRESS";
            const countUrl = `/scanner?barcode=${encodeURIComponent(t.barcode)}&task=${t.id}`;
            const result = t.result_status ? StockFlow.badge(t.result_status) : "";

            return `
            <article class="task p-${t.priority.toLowerCase()}">
                <span class="task-rail" aria-hidden="true"></span>
                <div class="task-main">
                    <div class="task-title">
                        ${e(t.product_name)}
                        <span class="badge ${t.priority === "HIGH" ? "badge-red" : t.priority === "MEDIUM" ? "badge-amber" : "badge-blue"}">${t.priority.charAt(0) + t.priority.slice(1).toLowerCase()}</span>
                        ${t.status === "IN_PROGRESS" ? '<span class="badge plain">Counting</span>' : ""}
                        ${t.status === "CANCELLED" ? '<span class="badge plain">Cancelled</span>' : ""}
                        ${result}
                    </div>
                    <div class="task-reason">${e(t.reason_text)}</div>
                    <div class="task-meta">
                        <span><code>${e(t.sku)}</code></span>
                        <span>${e(t.category || "")}</span>
                        <span>${t.assignee ? `Assigned to ${e(t.assignee)}` : "Unassigned"}</span>
                        <span>Requested by ${e(t.created_by)}</span>
                        ${open ? `<span>${dueText(t)}</span>` : `<span>Closed ${StockFlow.formatDate(t.completed_at)}${t.completed_by ? " by " + e(t.completed_by) : ""}</span>`}
                    </div>
                    ${t.note ? `<div class="task-note">${e(t.note)}</div>` : ""}
                </div>
                <div class="task-actions">
                    ${open ? `<a class="small-button solid" href="${countUrl}">Count now</a>` : ""}
                    ${open && t.status === "OPEN" ? `<button class="small-button" data-action="start" data-id="${t.id}">I'm on it</button>` : ""}
                    ${open && isManager ? `<button class="small-button" data-action="edit" data-id="${t.id}">Reassign</button>` : ""}
                    ${open && isManager ? `<button class="small-button danger" data-action="cancel" data-id="${t.id}">Cancel</button>` : ""}
                </div>
            </article>`;
        }).join("");
    }

    async function load() {

        try {
            const result = await StockFlow.api(`/api/checks/?status=${status}&scope=${scope()}`);
            tasks = result.data;
            renderSummary(result.summary);
            render();
        } catch (error) {
            listEl.innerHTML = `<p class="empty-state">${e(error.message)}</p>`;
        }
    }

    async function loadFormOptions() {

        if (assigneesLoaded) return;

        const [products, users] = await Promise.all([
            StockFlow.api("/api/products/"),
            StockFlow.api("/api/checks/assignees"),
        ]);

        form.product_id.innerHTML = products.data.map((p) =>
            `<option value="${p.id}">${e(p.name)} (${e(p.sku)}), ${p.quantity} in system</option>`).join("");

        form.assigned_to.innerHTML = '<option value="">Automatic</option>' + users.data.map((u) =>
            `<option value="${u.id}">${e(u.username)} (${e(u.role)})</option>`).join("");

        assigneesLoaded = true;
    }

    async function openForm(task = null) {

        try { await loadFormOptions(); } catch (error) { return StockFlow.toast(error.message, "error"); }

        form.reset();
        form.id.value = task?.id || "";
        document.getElementById("product-field").hidden = Boolean(task);
        form.product_id.required = !task;
        document.getElementById("check-modal-title").textContent = task ? `Reassign ${task.product_name}` : "Request a count";
        document.getElementById("check-submit").textContent = task ? "Save changes" : "Send request";

        if (task) {
            form.assigned_to.value = task.assigned_to || "";
            form.priority.value = task.priority;
            form.note.value = task.note || "";
        }

        StockFlow.openModal("check-modal");
    }

    form?.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const id = data.id;

        try {
            if (id) {
                await StockFlow.api(`/api/checks/${id}`, {
                    method: "PUT",
                    body: { assigned_to: data.assigned_to || null, priority: data.priority, note: data.note },
                });
                StockFlow.toast("Check updated. The new assignee has been notified.");
            } else {
                const result = await StockFlow.api("/api/checks/", {
                    method: "POST",
                    body: {
                        product_id: Number(data.product_id), assigned_to: data.assigned_to || null,
                        priority: data.priority, note: data.note,
                    },
                });
                StockFlow.toast(`Count requested. ${result.data.assignee || "Staff"} has been notified.`);
            }

            StockFlow.closeModal("check-modal");
            load();
            window.StockFlowAlerts?.refresh();

        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    listEl.addEventListener("click", async (event) => {

        const button = event.target.closest("button[data-action]");
        if (!button) return;

        const task = tasks.find((t) => t.id === Number(button.dataset.id));
        const action = button.dataset.action;

        if (action === "edit") return openForm(task);
        if (action === "cancel" && !confirm(`Cancel the count for ${task.product_name}?`)) return;

        try {
            await StockFlow.api(`/api/checks/${task.id}/${action}`, { method: "POST" });
            StockFlow.toast(action === "start" ? "Marked as counting." : "Check cancelled.");
            load();
            window.StockFlowAlerts?.refresh();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    document.querySelectorAll(".tab[data-status]").forEach((tab) => tab.addEventListener("click", () => {
        status = tab.dataset.status;
        document.querySelectorAll(".tab[data-status]").forEach((t) => t.classList.toggle("active", t === tab));
        load();
    }));

    document.querySelectorAll('input[name="scope"]').forEach((r) => r.addEventListener("change", load));
    document.getElementById("new-check")?.addEventListener("click", () => openForm());

    document.getElementById("run-scan")?.addEventListener("click", async (event) => {

        const button = event.currentTarget;
        button.disabled = true;

        try {
            const result = await StockFlow.api("/api/checks/run", { method: "POST" });
            const n = result.data.created;
            StockFlow.toast(n ? `${n} new check${n === 1 ? "" : "s"} created and staff notified.` : "No new checks needed.");
            load();
            window.StockFlowAlerts?.refresh();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    // Desktop alert prompt
    const prompt = document.getElementById("desktop-prompt");
    const showPrompt = () => { prompt.hidden = !("Notification" in window) || Notification.permission !== "default"; };

    document.getElementById("desktop-enable").addEventListener("click", async () => {
        const result = await Notification.requestPermission();
        StockFlow.toast(result === "granted" ? "Desktop alerts are on." : "Desktop alerts stay off.", result === "granted" ? "success" : "warning");
        showPrompt();
        window.StockFlowAlerts?.updateDesktopButton();
    });

    document.addEventListener("sf:checks", () => status === "open" && load());

    showPrompt();
    load();
})();
