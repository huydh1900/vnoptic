import {canPreview, getUrl} from "../../utils.esm";

const MODAL_ID = "attachment-preview-binary-modal";

function getOrCreateModal() {
    let modal = document.getElementById(MODAL_ID);
    if (modal) {
        return modal;
    }
    modal = document.createElement("div");
    modal.id = MODAL_ID;
    modal.style.cssText = [
        "position:fixed",
        "inset:0",
        "z-index:1200",
        "display:none",
        "background:rgba(0,0,0,.45)",
    ].join("; ");
    modal.innerHTML = `
        <div style="
            position:absolute;top:4%;left:4%;width:92%;height:92%;
            background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 16px 42px rgba(0,0,0,.35);
        ">
            <a data-role="download" style="
                position:absolute;top:10px;right:72px;z-index:2;border:none;background:#0f766e;color:#fff;
                width:34px;height:32px;border-radius:8px;cursor:pointer;text-decoration:none;font-size:18px;
                display:flex;align-items:center;justify-content:center;line-height:1;
            " title="Download" aria-label="Download" target="_blank" rel="noopener noreferrer">
                <i class="fa fa-download" role="img" aria-label="Download"></i>
            </a>
            <button type="button" data-role="close" style="
                position:absolute;top:10px;right:16px;z-index:2;border:none;background:#222;color:#fff;
                width:32px;height:32px;border-radius:16px;cursor:pointer;
            ">×</button>
            <iframe data-role="iframe" style="width:100%;height:100%;border:0;"></iframe>
        </div>
    `;
    modal.addEventListener("click", (ev) => {
        if (ev.target === modal || ev.target.dataset.role === "close") {
            hideModal(modal);
        }
    });
    document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape" && modal.style.display !== "none") {
            hideModal(modal);
        }
    });
    document.body.appendChild(modal);
    return modal;
}

function hideModal(modal) {
    const iframe = modal.querySelector('[data-role="iframe"]');
    if (iframe) {
        iframe.setAttribute("src", "about:blank");
    }
    modal.style.display = "none";
}

function getFilename(link) {
    const href = link.getAttribute("href") || "";
    const url = new URL(href, window.location.origin);
    const fromQuery = url.searchParams.get("filename");
    if (fromQuery) return fromQuery;

    const fromAttachmentTitle = link.closest(".o_attachment")?.getAttribute("title");
    if (fromAttachmentTitle) return fromAttachmentTitle;

    const fromImageExt = link.querySelector(".o_image")?.dataset.ext;
    if (fromImageExt) return `file.${fromImageExt}`;

    const fromDownload = link.getAttribute("download");
    if (fromDownload) return fromDownload;
    return (link.textContent || "").trim();
}

function getExtension(fileName) {
    if (!fileName || !fileName.includes(".")) return "";
    return fileName.split(".").pop().toLowerCase();
}

function getBinaryAttachmentLink(target) {
    const link = target.closest("a[href*='/web/content']");
    if (!link) return null;
    const inBinary = !!link.closest(".oe_fileupload, .o_attachments, .o_attachment_many2many");
    return inBinary ? link : null;
}

function getInlinePreviewUrl(link) {
    const href = link.getAttribute("href") || "";
    const url = new URL(href, window.location.origin);
    url.searchParams.set("download", "false");
    return `${url.pathname}?${url.searchParams.toString()}`;
}

function getInlineDownloadUrl(link) {
    const href = link.getAttribute("href") || "";
    const url = new URL(href, window.location.origin);
    url.searchParams.set("download", "true");
    return `${url.pathname}?${url.searchParams.toString()}`;
}

function getPreviewUrl(link, extension, filename) {
    const browserPreviewable = new Set([
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "bmp",
        "svg",
    ]);
    if (browserPreviewable.has(extension)) {
        return getInlinePreviewUrl(link);
    }
    return getUrl(null, link.href, extension, filename);
}

function updateDownloadButton(download, link, extension, filename) {
    if (!download) return;
    if (extension === "pdf") {
        download.style.display = "none";
        download.removeAttribute("href");
        download.removeAttribute("download");
        return;
    }
    download.style.display = "inline-flex";
    download.setAttribute("href", getInlineDownloadUrl(link));
    download.setAttribute("download", filename || "");
}

document.addEventListener(
    "click",
    (ev) => {
        const link = getBinaryAttachmentLink(ev.target);
        if (!link) return;

        const filename = getFilename(link);
        const extension = getExtension(filename);
        if (!canPreview(extension)) return;

        ev.preventDefault();
        ev.stopPropagation();

        const modal = getOrCreateModal();
        const iframe = modal.querySelector('[data-role="iframe"]');
        const download = modal.querySelector('[data-role="download"]');
        iframe.setAttribute("src", getPreviewUrl(link, extension, filename));
        updateDownloadButton(download, link, extension, filename);
        modal.style.display = "block";
    },
    true
);
