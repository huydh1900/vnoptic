/** @odoo-module **/

const TEXT_WRAPPER_CLASS = "o_preview_long_text_value";

const ensureTextWrapper = (cell) => {
    const existing = cell.querySelector(`.${TEXT_WRAPPER_CLASS}`);
    if (existing) {
        return existing;
    }

    const widget = cell.querySelector(".o_field_widget, .o_field_text");
    if (widget) {
        widget.classList.add(TEXT_WRAPPER_CLASS);
        return widget;
    }

    const hasElementChild = Array.from(cell.childNodes).some((node) => node.nodeType === Node.ELEMENT_NODE);
    if (hasElementChild) {
        const firstElement = cell.firstElementChild;
        if (firstElement) {
            firstElement.classList.add(TEXT_WRAPPER_CLASS);
            return firstElement;
        }
    }

    const wrapper = document.createElement("span");
    wrapper.className = TEXT_WRAPPER_CLASS;
    wrapper.textContent = (cell.textContent || "").trim();
    cell.textContent = "";
    cell.appendChild(wrapper);
    return wrapper;
};

const applyTitle = (element) => {
    const target = ensureTextWrapper(element);
    const text = (target.textContent || "").trim();
    if (text) {
        target.setAttribute("title", text);
    }
};

const scanAndApplyTitles = (root) => {
    root.querySelectorAll(".o_preview_long_text").forEach((el) => {
        applyTitle(el);
    });
};

const initPreviewLongTextTooltips = () => {
    scanAndApplyTitles(document);

    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType !== Node.ELEMENT_NODE) {
                    return;
                }
                const element = node;
                if (element.matches && element.matches(".o_preview_long_text")) {
                    applyTitle(element);
                }
                scanAndApplyTitles(element);
            });
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
};

document.addEventListener("DOMContentLoaded", initPreviewLongTextTooltips);
