/* B2B order line picker — cascade Brand → Model → Color trong row của bảng đơn.
 * Vanilla JS, không phải @odoo-module (load như script frontend đơn giản).
 */
(function () {
    "use strict";

    const URL_BRANDS = "/my/b2b/products/brands";
    const URL_MODELS = "/my/b2b/products/models";
    const URL_COLORS = "/my/b2b/products/colors";

    async function fetchJSON(url) {
        const r = await fetch(url, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });
        if (!r.ok) throw new Error("http " + r.status);
        return r.json();
    }

    function fillSelect(sel, items, placeholder, valueKey, labelKey) {
        sel.innerHTML = "";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = placeholder;
        sel.appendChild(opt0);
        (items || []).forEach((it) => {
            const o = document.createElement("option");
            o.value = String(it[valueKey] == null ? "" : it[valueKey]);
            o.textContent = it[labelKey];
            if (it.product_id != null) {
                o.dataset.productId = it.product_id;
            }
            sel.appendChild(o);
        });
    }

    // Lấy đuôi cuối của mã model: ưu tiên cụm số ở cuối (vd VY25-A-VZ8086 → 8086),
    // fallback phần sau dấu '-' cuối cùng.
    function modelShortLabel(m) {
        const s = String(m == null ? "" : m);
        const md = s.match(/(\d+)\s*$/);
        if (md) return md[1];
        const parts = s.split("-");
        return parts[parts.length - 1] || s;
    }

    // Combobox cho Model: nút toggle giống .form-select + panel chứa search + danh sách.
    // Expose API tương tự <select>: value, disabled, setItems, addEventListener('change'), focus.
    function buildModelCombo(comboEl) {
        const toggle = comboEl.querySelector(".b2b-model-toggle");
        const toggleText = comboEl.querySelector(".b2b-model-toggle-text");
        const panel = comboEl.querySelector(".b2b-model-panel");
        const searchInp = comboEl.querySelector(".b2b-model-search");
        const listEl = comboEl.querySelector(".b2b-model-list");
        const placeholder = toggleText.textContent;
        let items = [];
        let value = "";
        const changeCbs = [];

        function updateToggleText() {
            if (!value) {
                toggleText.textContent = placeholder;
                toggleText.classList.add("text-muted");
            } else {
                toggleText.textContent = modelShortLabel(value);
                toggleText.classList.remove("text-muted");
            }
        }
        function renderList(query) {
            listEl.innerHTML = "";
            const q = (query || "").toLowerCase().trim();
            let count = 0;
            items.forEach((it) => {
                const full = String(it.model == null ? "" : it.model);
                const short = modelShortLabel(full);
                if (q && short.toLowerCase().indexOf(q) === -1 && full.toLowerCase().indexOf(q) === -1) return;
                const li = document.createElement("li");
                li.className = "px-2 py-1 b2b-model-item";
                li.style.cursor = "pointer";
                li.textContent = short;
                li.title = full;
                li.addEventListener("mouseenter", () => li.classList.add("bg-light"));
                li.addEventListener("mouseleave", () => li.classList.remove("bg-light"));
                li.addEventListener("click", () => {
                    value = full;
                    updateToggleText();
                    closePanel();
                    changeCbs.forEach((cb) => cb());
                });
                listEl.appendChild(li);
                count++;
            });
            if (!count) {
                const li = document.createElement("li");
                li.className = "px-2 py-1 text-muted small";
                li.textContent = "(không có)";
                listEl.appendChild(li);
            }
        }
        function isOpen() { return panel.style.display !== "none" && panel.dataset.open === "1"; }
        function positionPanel() {
            const rect = toggle.getBoundingClientRect();
            panel.style.position = "fixed";
            panel.style.top = rect.bottom + "px";
            panel.style.left = rect.left + "px";
            panel.style.width = rect.width + "px";
            panel.style.right = "auto";
        }
        function openPanel() {
            if (toggle.disabled) return;
            searchInp.value = "";
            renderList("");
            if (panel.parentElement !== document.body) {
                document.body.appendChild(panel);
            }
            panel.style.display = "";
            panel.dataset.open = "1";
            positionPanel();
            searchInp.style.display = items.length > 6 ? "" : "none";
            if (items.length > 6) {
                setTimeout(() => searchInp.focus(), 0);
            }
        }
        function closePanel() {
            panel.style.display = "none";
            panel.dataset.open = "0";
        }

        toggle.addEventListener("click", function (ev) {
            ev.stopPropagation();
            isOpen() ? closePanel() : openPanel();
        });
        searchInp.addEventListener("input", () => renderList(searchInp.value));
        panel.addEventListener("click", (ev) => ev.stopPropagation());
        document.addEventListener("click", (ev) => {
            if (!comboEl.contains(ev.target) && !panel.contains(ev.target)) closePanel();
        });
        window.addEventListener("scroll", () => { if (isOpen()) positionPanel(); }, true);
        window.addEventListener("resize", () => { if (isOpen()) positionPanel(); });

        const api = {
            get value() { return value; },
            set value(v) {
                value = String(v == null ? "" : v);
                updateToggleText();
            },
            get disabled() { return toggle.disabled; },
            set disabled(b) {
                toggle.disabled = !!b;
                if (b) closePanel();
            },
            setItems(arr) {
                items = arr || [];
                if (isOpen()) renderList(searchInp.value);
            },
            addEventListener(name, cb) {
                if (name === "change") changeCbs.push(cb);
                else if (name === "keydown") {
                    toggle.addEventListener("keydown", cb);
                    searchInp.addEventListener("keydown", cb);
                }
            },
            focus() { toggle.focus(); },
            _closePanel: closePanel,
        };
        updateToggleText();
        return api;
    }

    function getCsrfToken() {
        const el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : "";
    }

    function getAddUrl() {
        const updForm = document.querySelector('form[action*="/line/update"]');
        if (updForm && updForm.action) {
            return updForm.action.replace("/line/update", "/line/add");
        }
        return "";
    }

    function setupCascade(addRows, cascadeRow) {
        const selBrand = cascadeRow.querySelector(".b2b-sel-brand");
        const modelComboEl = cascadeRow.querySelector(".b2b-model-combo");
        const selModel = buildModelCombo(modelComboEl);
        const selColor = cascadeRow.querySelector(".b2b-sel-color");
        const inpQty = cascadeRow.querySelector(".b2b-cascade-qty");
        const sttCell = cascadeRow.querySelector(".b2b-cascade-stt");
        let submitting = false;
        let brandsLoaded = false;
        let brandsLoading = null;

        async function loadBrands() {
            if (brandsLoaded) return;
            if (brandsLoading) return brandsLoading;
            brandsLoading = (async () => {
                try {
                    const d = await fetchJSON(URL_BRANDS);
                    fillSelect(selBrand, d.results || [], "-- Thương hiệu --", "id", "name");
                    selBrand.disabled = false;
                    brandsLoaded = true;
                } catch (e) {
                    // giữ placeholder hiện tại, cho phép thử lại
                } finally {
                    brandsLoading = null;
                }
            })();
            return brandsLoading;
        }

        function resetState() {
            selBrand.value = "";
            selModel.value = "";
            selModel.setItems([]);
            selModel.disabled = true;
            fillSelect(selColor, [], "-- Mã màu --", "color", "color");
            selColor.disabled = true;
            inpQty.value = "1";
        }

        async function submitAdd(productId) {
            if (submitting || !productId) return;
            const url = getAddUrl();
            if (!url) return;
            submitting = true;
            selBrand.disabled = true;
            selModel.disabled = true;
            selColor.disabled = true;
            inpQty.disabled = true;
            const fd = new FormData();
            fd.append("csrf_token", getCsrfToken());
            fd.append("product_id", productId);
            fd.append("qty", String(Math.max(1, parseInt(inpQty.value, 10) || 1)));
            try {
                const resp = await fetch(url, {
                    method: "POST",
                    body: fd,
                    credentials: "same-origin",
                });
                if (resp.ok || resp.redirected) {
                    window.location.reload();
                    return;
                }
            } catch (e) {
                // fallthrough
            }
            submitting = false;
            selBrand.disabled = false;
            selModel.disabled = false;
            selColor.disabled = false;
            inpQty.disabled = false;
        }

        function nextStt() {
            for (const r of addRows) {
                const n = parseInt(r.dataset.lineCount || "", 10);
                if (!isNaN(n)) return n + 1;
            }
            return 1;
        }

        function openCascade(fromRow) {
            // Hiện row ngay → tránh cảm giác delay chờ network.
            resetState();
            if (sttCell) sttCell.textContent = String(nextStt());
            addRows.forEach((r) => (r.style.display = "none"));
            // Chèn cascade row ngay sau button được click.
            if (fromRow && fromRow.parentNode) {
                fromRow.parentNode.insertBefore(cascadeRow, fromRow.nextSibling);
            }
            cascadeRow.style.display = "";
            if (!brandsLoaded) {
                selBrand.disabled = true;
                fillSelect(selBrand, [], "Đang tải thương hiệu…", "id", "name");
                loadBrands().then(() => {
                    if (cascadeRow.style.display !== "none") selBrand.focus();
                });
            } else {
                selBrand.focus();
            }
        }

        function closeCascade() {
            cascadeRow.style.display = "none";
            addRows.forEach((r) => (r.style.display = ""));
            resetState();
        }

        addRows.forEach((row) => {
            const btn = row.querySelector(".b2b-add-line-btn");
            if (btn) btn.addEventListener("click", () => openCascade(row));
        });

        selBrand.addEventListener("change", async function () {
            fillSelect(selColor, [], "-- Mã màu --", "color", "color");
            selColor.disabled = true;
            selModel.value = "";
            if (!selBrand.value) {
                selModel.setItems([]);
                selModel.disabled = true;
                return;
            }
            try {
                const d = await fetchJSON(URL_MODELS + "?brand_id=" + encodeURIComponent(selBrand.value));
                selModel.setItems(d.results || []);
                selModel.disabled = false;
            } catch (e) {
                selModel.setItems([]);
                selModel.disabled = true;
            }
        });

        selModel.addEventListener("change", async function () {
            if (!selBrand.value || !selModel.value) {
                fillSelect(selColor, [], "-- Mã màu --", "color", "color");
                selColor.disabled = true;
                return;
            }
            try {
                const url =
                    URL_COLORS +
                    "?brand_id=" + encodeURIComponent(selBrand.value) +
                    "&opt_model=" + encodeURIComponent(selModel.value);
                const d = await fetchJSON(url);
                fillSelect(selColor, d.results || [], "-- Mã màu --", "color", "color");
                selColor.disabled = false;
            } catch (e) {
                fillSelect(selColor, [], "-- Mã màu --", "color", "color");
                selColor.disabled = true;
            }
        });

        // Chọn xong Mã màu → auto-add line (qty từ input, default 1).
        selColor.addEventListener("change", function () {
            const opt = selColor.selectedOptions[0];
            if (opt && opt.dataset.productId) submitAdd(opt.dataset.productId);
        });

        // Esc trên bất kỳ input nào → đóng cascade.
        [selBrand, selModel, selColor, inpQty].forEach((el) => {
            if (!el) return;
            el.addEventListener("keydown", function (ev) {
                if (ev.key === "Escape") {
                    ev.preventDefault();
                    closeCascade();
                }
            });
        });

        // Preload brands ngay khi setup → click "+ Thêm 1 dòng" không phải chờ network.
        loadBrands();
    }

    function init() {
        const cascadeRow = document.querySelector(".b2b-cascade-row");
        const addRows = Array.from(document.querySelectorAll(".b2b-add-row"));
        if (cascadeRow && addRows.length) {
            setupCascade(addRows, cascadeRow);
        }
    }
    // Asset có thể vào bundle lazy (load sau DOMContentLoaded) → bootstrap theo readyState.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
