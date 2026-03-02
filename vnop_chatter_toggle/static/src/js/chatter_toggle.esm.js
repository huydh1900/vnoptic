/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";
import { useEffect, useRef } from "@odoo/owl";

const COLLAPSED_CLASS = "o_vnop_chatter_collapsed";
const HANDLE_CLASS = "o_vnop_chatter_toggle_handle";
const INIT_CLASS = "o_vnop_chatter_toggle_initialized";

patch(FormRenderer.prototype, {
    setup() {
        super.setup(...arguments);

        this._vnopCompiledRootRef = useRef("compiled_view_root");

        useEffect(
            (rootEl, viewportSize) => {
                if (!rootEl) {
                    return;
                }
                const formViewEl = rootEl.closest(".o_form_view");
                if (!formViewEl) {
                    return;
                }
                this._vnopSyncChatterToggle(formViewEl, viewportSize);
            },
            () => [this._vnopCompiledRootRef.el, this.uiService.size]
        );
    },

    _vnopSyncChatterToggle(formViewEl) {
        const asideChatter = formViewEl.querySelector(".o-mail-Form-chatter.o-aside");
        const existingHandle = formViewEl.querySelector(`.${HANDLE_CLASS}`);

        if (!asideChatter) {
            formViewEl.classList.remove(COLLAPSED_CLASS);
            formViewEl.classList.remove(INIT_CLASS);
            if (existingHandle) {
                existingHandle.remove();
            }
            return;
        }

        // Default behavior: collapse chatter on first render of each form.
        if (!formViewEl.classList.contains(INIT_CLASS)) {
            formViewEl.classList.add(COLLAPSED_CLASS);
            formViewEl.classList.add(INIT_CLASS);
        }

        const handle = existingHandle || this._vnopCreateToggleHandle(formViewEl);
        this._vnopUpdateToggleHandle(handle, formViewEl.classList.contains(COLLAPSED_CLASS));
    },

    _vnopCreateToggleHandle(formViewEl) {
        const handle = document.createElement("button");
        handle.type = "button";
        handle.className = `btn btn-light ${HANDLE_CLASS}`;
        handle.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            const isCollapsed = formViewEl.classList.toggle(COLLAPSED_CLASS);
            this._vnopUpdateToggleHandle(handle, isCollapsed);
        });
        formViewEl.appendChild(handle);
        return handle;
    },

    _vnopUpdateToggleHandle(handle, isCollapsed) {
        handle.innerHTML = `<i class="fa ${isCollapsed ? "fa-angle-left" : "fa-angle-right"}"></i>`;
        handle.title = isCollapsed ? "Mở hội thoại" : "Thu gọn hội thoại";
        handle.setAttribute("aria-label", handle.title);
    },
});
