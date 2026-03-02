export function canPreview(extension) {
    const supported_extensions = [
        "odt",
        "odp",
        "ods",
        "fodt",
        "pdf",
        "ott",
        "fodp",
        "otp",
        "fods",
        "ots",
        "docx",
        "xlsx",
        "xlsm",
        "xltx",
        "xltm",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "bmp",
        "svg",
        "txt",
        "csv",
        "log",
        "md",
    ];
    return supported_extensions.includes(extension);
}

export function getUrl(
    attachment_id,
    attachment_url,
    attachment_extension,
    attachment_title
) {
    const base = window.location.origin || "";
    const params = new URLSearchParams();
    if (attachment_id) {
        params.set("aid", String(attachment_id));
    } else if (attachment_url) {
        const normalized = attachment_url.replace(base, "");
        params.set("src", normalized);
    }
    if (attachment_extension) {
        params.set("ext", attachment_extension);
    }
    if (attachment_title) {
        params.set("title", attachment_title);
    }
    return `${base}/attachment_preview/view?${params.toString()}`;
}

export function showPreview(
    attachment_id,
    attachment_url,
    attachment_extension,
    attachment_title,
    split_screen,
    attachment_info_list,
    bus = null
) {
    if (split_screen && attachment_info_list && bus) {
        bus.trigger("open_attachment_preview", {
            attachment_id,
            attachment_info_list,
        });
    } else {
        window.open(
            getUrl(
                attachment_id,
                attachment_url,
                attachment_extension,
                attachment_title
            ),
            "_blank",
            "noopener,noreferrer"
        );
    }
}
