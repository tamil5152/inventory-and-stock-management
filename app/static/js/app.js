/* StockFlow shared front-end helpers */

const StockFlow = (() => {

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

    async function api(url, options = {}) {

        const config = {
            method: options.method || "GET",
            headers: {
                "Accept": "application/json",
                "X-CSRFToken": csrfToken,
            },
            credentials: "same-origin",
        };

        if (options.body !== undefined) {
            config.headers["Content-Type"] = "application/json";
            config.body = JSON.stringify(options.body);
        }

        const response = await fetch(url, config);

        if (response.status === 401) {
            window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
            throw new Error("Session expired. Please log in again.");
        }

        let data = {};

        try {
            data = await response.json();
        } catch (_) {
            data = {};
        }

        if (!response.ok) {
            const error = new Error(data.error || `Request failed (${response.status})`);
            error.status = response.status;
            error.data = data;
            throw error;
        }

        return data;
    }

    function escapeHtml(value) {

        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function toast(message, type = "success") {

        const container = document.getElementById("toast-container");
        if (!container) return alert(message);

        const node = document.createElement("div");
        node.className = `toast toast-${type}`;
        node.textContent = message;
        container.appendChild(node);

        setTimeout(() => node.classList.add("hide"), 3500);
        setTimeout(() => node.remove(), 4000);
    }

    function parseDate(value) {

        if (!value) return null;
        // SQLite returns naive timestamps that are stored in UTC.
        const hasZone = /[zZ]|[+-]\d\d:?\d\d$/.test(value);
        return new Date(hasZone ? value : value + "Z");
    }

    function formatDate(value) {

        const date = parseDate(value);
        if (!date || isNaN(date)) return "-";

        return date.toLocaleString(undefined, {
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit",
        });
    }

    function money(value) {

        return "Rs. " + Number(value || 0).toLocaleString("en-IN", {
            minimumFractionDigits: 2, maximumFractionDigits: 2,
        });
    }

    const STATUS_LABELS = {
        IN_STOCK: ["In stock", "badge-green"],
        LOW_STOCK: ["Low stock", "badge-amber"],
        OUT_OF_STOCK: ["Out of stock", "badge-red"],
        MATCH: ["Match", "badge-green"],
        DISCREPANCY: ["Discrepancy", "badge-red"],
        UNKNOWN_BARCODE: ["Unknown barcode", "badge-amber"],
        STOCK_IN: ["Stock in", "move-stock_in"],
        STOCK_OUT: ["Stock out", "move-stock_out"],
        ADJUSTMENT: ["Adjustment", "move-adjustment"],
        HIGH: ["High", "risk-high"],
        MEDIUM: ["Medium", "risk-medium"],
        LOW: ["Low", "risk-low"],
    };

    function badge(status, extra = "") {

        const [label, cls] = STATUS_LABELS[status] || [status || "-", "badge-blue"];
        return `<span class="badge ${cls}">${escapeHtml(label)}${extra !== "" && extra !== undefined && extra !== null ? ", " + escapeHtml(extra) : ""}</span>`;
    }

    function hasRole(...roles) {

        return roles.includes(window.CURRENT_USER?.role);
    }

    function openModal(id) {

        const modal = document.getElementById(id);
        modal?.classList.add("open");
        modal?.querySelector("input:not([type=hidden]):not([disabled]), select, textarea")?.focus();
    }

    function closeModal(id) {

        document.getElementById(id)?.classList.remove("open");
    }

    function formData(form) {

        const data = {};
        new FormData(form).forEach((value, key) => { data[key] = typeof value === "string" ? value.trim() : value; });
        return data;
    }

    function debounce(fn, wait = 300) {

        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), wait);
        };
    }

    // Global UI wiring
    document.addEventListener("click", (event) => {

        const closer = event.target.closest("[data-close-modal]");
        if (closer) closeModal(closer.dataset.closeModal);

        if (event.target.classList.contains("modal")) {
            event.target.classList.remove("open");
        }
    });

    document.addEventListener("keydown", (event) => {

        if (event.key === "Escape") {
            document.querySelectorAll(".modal.open").forEach((m) => m.classList.remove("open"));
        }
    });

    document.addEventListener("DOMContentLoaded", () => {

        document.querySelectorAll(".local-time[data-time]").forEach((cell) => {
            if (cell.dataset.time && cell.dataset.time !== "None") {
                cell.textContent = formatDate(cell.dataset.time);
            }
        });
    });

    return {
        api, escapeHtml, toast, formatDate, money, badge, hasRole,
        openModal, closeModal, formData, debounce,
    };
})();
