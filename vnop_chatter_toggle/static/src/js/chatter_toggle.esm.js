/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";
import { useEffect, useRef } from "@odoo/owl";

const COLLAPSED_CLASS = "o_vnop_chatter_collapsed";
const HANDLE_CLASS = "o_vnop_chatter_toggle_handle";
const INIT_CLASS = "o_vnop_chatter_toggle_initialized";
const ANIMATING_CLASS = "o_vnop_chatter_animating";
const TRANSITION_DURATION_MS = 360;

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
        const icon = document.createElement("i");
        handle.appendChild(icon);
        handle.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            this._vnopToggleChatter(formViewEl, handle);
        });
        formViewEl.appendChild(handle);
        return handle;
    },

    _vnopToggleChatter(formViewEl, handle) {
        if (formViewEl.classList.contains(ANIMATING_CLASS)) {
            return;
        }

        const isCollapsed = formViewEl.classList.contains(COLLAPSED_CLASS);
        const nextCollapsed = !isCollapsed;
        formViewEl.classList.add(ANIMATING_CLASS);
        handle.disabled = true;

        requestAnimationFrame(() => {
            formViewEl.classList.toggle(COLLAPSED_CLASS, nextCollapsed);
            this._vnopUpdateToggleHandle(handle, nextCollapsed);
            this._vnopFinalizeToggleAnimation(formViewEl, handle);
        });
    },

    _vnopFinalizeToggleAnimation(formViewEl, handle) {
        const chatterAside = formViewEl.querySelector(".o-mail-Form-chatter.o-aside");
        const release = () => {
            formViewEl.classList.remove(ANIMATING_CLASS);
            handle.disabled = false;
        };
        if (!chatterAside) {
            release();
            return;
        }
        let done = false;
        const onDone = () => {
            if (done) {
                return;
            }
            done = true;
            chatterAside.removeEventListener("transitionend", onEnd);
            release();
        };
        const onEnd = (ev) => {
            if (ev.target === chatterAside) {
                onDone();
            }
        };
        chatterAside.addEventListener("transitionend", onEnd);
        window.setTimeout(onDone, TRANSITION_DURATION_MS);
    },

    _vnopUpdateToggleHandle(handle, isCollapsed) {
        const icon = handle.firstElementChild;
        if (icon) {
            icon.className = `fa ${isCollapsed ? "fa-angle-left" : "fa-angle-right"}`;
        }
        handle.title = isCollapsed ? "Mở hội thoại" : "Thu gọn hội thoại";
        handle.setAttribute("aria-label", handle.title);
    },
});
