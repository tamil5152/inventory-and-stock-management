/* Staff page (admin only) */

(() => {

    const e = StockFlow.escapeHtml;
    const body = document.getElementById("users-body");
    const form = document.getElementById("user-form");
    const shelfBox = document.getElementById("shelf-options");
    let users = [];
    let shelves = [];

    const PHONE_RE = /^\+?\d{10,15}$/;
    const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

    function shelfChips(list) {
        return list.length
            ? list.map((s) => `<span class="chip" title="${e(s.name)}">${e(s.code)}</span>`).join(" ")
            : '<span class="muted">None</span>';
    }

    async function load() {

        try {
            const [u, s] = await Promise.all([StockFlow.api("/api/users/"), StockFlow.api("/api/shelves/")]);
            users = u.data;
            shelves = s.data;

            body.innerHTML = users.map((user) => `
                <tr class="${user.is_active ? "" : "archived-row"}">
                    <td><div class="cell-title">${e(user.display_name)}${user.id === window.CURRENT_USER.id ? ' <small class="muted">(you)</small>' : ""}</div>
                        <div class="cell-sub">@${e(user.username)}</div></td>
                    <td><a class="cell-link" href="mailto:${e(user.email)}">${e(user.email)}</a><br>
                        ${user.phone ? `<a class="cell-link muted" href="tel:${e(user.phone)}">${e(user.phone)}</a>` : '<span class="muted">No mobile</span>'}</td>
                    <td><span class="badge badge-blue plain">${e(user.role.charAt(0).toUpperCase() + user.role.slice(1))}</span></td>
                    <td>${shelfChips(user.shelves)}</td>
                    <td>${user.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge">Disabled</span>'}</td>
                    <td class="actions">
                        <button class="small-button" data-action="edit" data-id="${user.id}">Edit</button>
                        ${user.id !== window.CURRENT_USER.id ? `<button class="small-button ${user.is_active ? "danger" : ""}" data-action="toggle" data-id="${user.id}">${user.is_active ? "Disable" : "Enable"}</button>` : ""}
                    </td>
                </tr>`).join("");
        } catch (error) {
            body.innerHTML = `<tr><td colspan="6" class="empty-state">${e(error.message)}</td></tr>`;
        }
    }

    function renderShelfOptions(selected = []) {

        if (!shelves.length) {
            shelfBox.innerHTML = '<p class="muted">No shelves yet. Create shelves first, then assign them here.</p>';
            return;
        }

        shelfBox.innerHTML = shelves.map((s) => `
            <label class="check-tile">
                <input type="checkbox" name="shelf_ids" value="${s.id}" ${selected.includes(s.id) ? "checked" : ""}>
                <span><strong>${e(s.code)}</strong> ${e(s.name)}
                ${s.staff.length ? `<small class="muted">Now: ${e(s.staff.map((p) => p.name).join(", "))}</small>` : '<small class="muted">Nobody yet</small>'}</span>
            </label>`).join("");
    }

    function openForm(user = null) {

        form.reset();
        form.id.value = user?.id || "";
        form.username.disabled = Boolean(user);
        form.password.required = !user;

        document.getElementById("password-label").textContent = user
            ? "New password (leave empty to keep the current one)"
            : "Temporary password * (min 8 characters)";
        document.getElementById("user-modal-title").textContent = user ? `Edit ${user.display_name}` : "Add staff member";
        document.getElementById("user-submit").textContent = user ? "Save changes" : "Add staff member";

        if (user) {
            form.full_name.value = user.full_name || "";
            form.email.value = user.email;
            form.phone.value = user.phone || "";
            form.role.value = user.role;
            form.username.value = user.username;
        }

        renderShelfOptions(user ? user.shelves.map((s) => s.id) : []);
        StockFlow.openModal("user-modal");
    }

    // Client-side checks for quick feedback; the server validates everything again.
    function validate(data, isNew) {

        const phone = (data.phone || "").replace(/[\s\-()]/g, "");

        if (!data.full_name) return "Enter the staff member's full name.";
        if (!EMAIL_RE.test(data.email || "")) return "Enter a valid e-mail address.";
        if (!PHONE_RE.test(phone)) return "Enter a valid mobile number, for example +91 98765 43210.";
        if (isNew && !data.username) return "Choose a username.";
        if (isNew && (data.password || "").length < 8) return "The password needs at least 8 characters.";
        if (!isNew && data.password && data.password.length < 8) return "The new password needs at least 8 characters.";
        return null;
    }

    form.addEventListener("submit", async (event) => {

        event.preventDefault();
        const data = StockFlow.formData(form);
        const id = data.id;
        const shelfIds = [...form.querySelectorAll('input[name="shelf_ids"]:checked')].map((i) => Number(i.value));

        const problem = validate(data, !id);
        if (problem) return StockFlow.toast(problem, "warning");

        const payload = {
            full_name: data.full_name, email: data.email, phone: data.phone,
            role: data.role, shelf_ids: shelfIds,
        };
        if (data.password) payload.password = data.password;

        const button = document.getElementById("user-submit");
        button.disabled = true;

        try {
            if (id) {
                await StockFlow.api(`/api/users/${id}`, { method: "PUT", body: payload });
                StockFlow.toast("Staff member updated.");
            } else {
                payload.username = data.username;
                await StockFlow.api("/api/users/", { method: "POST", body: payload });
                StockFlow.toast(`${data.full_name} added. A welcome e-mail has been sent.`);
            }

            StockFlow.closeModal("user-modal");
            load();

        } catch (error) {
            StockFlow.toast(error.message, "error");
        } finally {
            button.disabled = false;
        }
    });

    body.addEventListener("click", async (event) => {

        const button = event.target.closest("button[data-action]");
        if (!button) return;

        const user = users.find((u) => u.id === Number(button.dataset.id));

        if (button.dataset.action === "edit") return openForm(user);

        try {
            await StockFlow.api(`/api/users/${user.id}`, { method: "PUT", body: { is_active: !user.is_active } });
            StockFlow.toast(user.is_active ? `${user.display_name} disabled.` : `${user.display_name} enabled.`);
            load();
        } catch (error) {
            StockFlow.toast(error.message, "error");
        }
    });

    async function loadMailStatus() {

        const text = document.getElementById("mail-status-text");
        const input = document.getElementById("test-email-to");

        try {
            const s = (await StockFlow.api("/api/users/email-status")).data;
            input.value = s.admin_email || "";

            text.innerHTML = s.enabled
                ? `E-mails are sent from <strong>${e(s.sender)}</strong> through ${e(s.server)}. ` +
                  (s.admin_email ? `A copy of every job assignment goes to <strong>${e(s.admin_email)}</strong>.` : "Set ADMIN_EMAIL in .env to get a copy of every job.")
                : "E-mail is off. Add your Gmail settings to the .env file and restart the app. In-app notifications still work.";
            document.getElementById("mail-status").classList.toggle("off", !s.enabled);
        } catch (error) {
            text.textContent = error.message;
        }
    }

    document.getElementById("test-email-btn").addEventListener("click", async (event) => {

        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = "Sending…";

        try {
            const result = await StockFlow.api("/api/users/test-email", {
                method: "POST", body: { to: document.getElementById("test-email-to").value.trim() },
            });
            StockFlow.toast(result.message);
        } catch (error) {
            StockFlow.toast(error.message, "error");
        } finally {
            button.disabled = false;
            button.textContent = "Send test e-mail";
        }
    });

    document.getElementById("add-user-btn").addEventListener("click", () => openForm());

    loadMailStatus();
    load();
})();
