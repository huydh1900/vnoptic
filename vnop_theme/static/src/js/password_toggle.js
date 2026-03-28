/** @odoo-module **/

function setupPasswordToggle(input) {
    if (!input || input.dataset.vnopToggleReady === "1") {
        return;
    }

    input.dataset.vnopToggleReady = "1";

    const wrapper = document.createElement("div");
    wrapper.className = "vnop-password-wrap";

    const parent = input.parentNode;
    parent.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "vnop-password-toggle";
    button.setAttribute("aria-label", "Hiện mật khẩu");
    button.innerHTML = '<i class="fa fa-eye" aria-hidden="true"></i>';

    button.addEventListener("click", () => {
        const isHidden = input.type === "password";
        input.type = isHidden ? "text" : "password";
        button.setAttribute("aria-label", isHidden ? "Ẩn mật khẩu" : "Hiện mật khẩu");
        button.innerHTML = isHidden
            ? '<i class="fa fa-eye-slash" aria-hidden="true"></i>'
            : '<i class="fa fa-eye" aria-hidden="true"></i>';
    });

    wrapper.appendChild(button);
}

function initPasswordToggles() {
    const selectors = [
        ".vnop-theme-login .oe_login_form input[type='password']",
        ".vnop-theme-login .oe_signup_form input[type='password']",
        ".vnop-theme-login .oe_reset_password_form input[type='password']",
    ];

    document.querySelectorAll(selectors.join(",")).forEach(setupPasswordToggle);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPasswordToggles);
} else {
    initPasswordToggles();
}
