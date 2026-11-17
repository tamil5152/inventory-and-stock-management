/* Users page (admin only) */

(() => {

    const e = StockFlow.escapeHtml;
    const body = document.getElementById("users-body");
    const form = document.getElementById("user-form");
    let users = [];

    async function load() {

        try {
            users = (await StockFlow.api("/api/users/")).data;
            body.innerHTML = users.map((u) => `
                <tr class="${u.is_active ? "" : "archived-row"}">
                    <td><strong>${e(u.username)}</strong>${u.id === window.CURRENT_USER.id ? ' <small class="muted">(you)</small>' : ""}</td>
                    <td>${e(u.email)}</td>
                    <td><span class="badge badge-blue">${e(u.role)}</span></td>
                    <td>${u.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge">Disabled</span>'}</td>
                    <td>${StockFlow.formatDate(u.created_at)}</td>
                    <td class="actions">
                        <button class="small-button" data-action="edit" data-id="${u.id}">Edit</button>
                        ${u.id !== window.CURRENT_USER.id ? `<button class="small-button ${u.is_active ? "danger" : ""}" data-action="toggle" data-id="${u.id}">${u.is_active ? "Disable" : "Enable"}</button>` : ""}
                    </td>
                </tr>`).join("");
        } catch (error) {
            body.innerHTML = `<tr><td colspan="6" class="empty-state">${e(error.message)}</td></tr>`;
        }
    }

    function openForm(user = null) {

        form.reset();
        form.id.value = user?.id || "";
        form.username.disabled = Boolean(user);
        form.email.disabled = Boolean(user);
        form.password.required = !user;
        document.getElementById("password-label").textContent = user ? "New password (optional)" : "Password * (min 8)";
        document.getElementById("user-modal-title").textContent = user ? `Edit ${user.username}` : "Add user";

        if (user) {
            form.username.value = user.username;
            form.email.value = user.email;
            form.role.value = user.role;
        }

        StockFlow.openModal("user-modal");
    }

    form.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const id = data.id;

        try {
            if (id) {
                const body = { role: data.role };
                if (data.password) body.password = data.password;
                await StockFlow.api(`/api/users/${id}`, { method: "PUT", body });
            } else {
                delete data.id;
                await StockFlow.api("/api/users/", { method: "POST", body: data });
            }

            StockFlow.toast(id ? "User updated." : "User created.");
            StockFlow.closeModal("user-modal");
            load();

        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    body.addEventListener("click", async (event) => {

        const button = event.target.closest("button[data-action]");
        if (!button) return;

        const user = users.find((u) => u.id === Number(button.dataset.id));

        if (button.dataset.action === "edit") return openForm(user);

        try {
            await StockFlow.api(`/api/users/${user.id}`, { method: "PUT", body: { is_active: !user.is_active } });
            StockFlow.toast("User status changed.");
            load();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    document.getElementById("add-user-btn").addEventListener("click", () => openForm());

    load();
})();
