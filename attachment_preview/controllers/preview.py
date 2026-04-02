# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import base64
import html
import io
import mimetypes
import re
import zipfile
from urllib.parse import parse_qs, quote, urlencode, urlparse
from xml.etree import ElementTree as ET

from odoo import http
from odoo.http import request

DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
OASIS_EXTENSIONS = {
    "odt",
    "odp",
    "ods",
    "fodt",
    "ott",
    "fodp",
    "otp",
    "fods",
    "ots",
}


class AttachmentPreviewController(http.Controller):
    @http.route("/attachment_preview/view", type="http", auth="user", methods=["GET"])
    def attachment_preview_view(self, aid=None, src=None, title=None, ext=None, **kwargs):
        resolved = self._resolve_payload(aid=aid, src=src, title=title, ext=ext)
        if not resolved:
            return request.not_found()

        filename = resolved["filename"]
        extension = resolved["extension"]
        payload = resolved["payload"]
        preview_url = resolved["preview_url"]
        download_url = resolved["download_url"]

        if extension == "pdf":
            body = self._render_pdf(preview_url)
        elif extension in {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"}:
            body = self._render_image(preview_url, filename)
        elif extension == "docx":
            body = self._render_docx(payload, filename)
        elif extension in {"xlsx", "xlsm", "xltx", "xltm"}:
            body = self._render_xlsx(payload, filename)
        elif extension in OASIS_EXTENSIONS:
            body = self._render_viewerjs(preview_url, filename, extension)
        elif extension in {"csv", "txt", "log", "md"}:
            body = self._render_text(payload, filename)
        else:
            body = self._render_unsupported(filename, extension)

        html_page = self._shell(filename or "Attachment Preview", body, download_url)
        return request.make_response(
            html_page,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    def _resolve_payload(self, aid=None, src=None, title=None, ext=None):
        if aid:
            attachment = request.env["ir.attachment"].browse(int(aid)).exists()
            if not attachment:
                return None
            attachment.check("read")
            filename = attachment.name or (title or "")
            payload = base64.b64decode(attachment.datas or b"")
            preview_url = f"/web/content/{attachment.id}?model=ir.attachment&download=false"
            download_url = f"/web/content/{attachment.id}?model=ir.attachment&download=true"
            extension = self._extract_extension(filename, ext=ext)
            return {
                "filename": filename,
                "payload": payload,
                "preview_url": preview_url,
                "download_url": download_url,
                "extension": extension,
            }

        if not src:
            return None

        parsed = urlparse(src)
        if parsed.netloc and parsed.netloc != request.httprequest.host:
            return None

        path = parsed.path or ""
        params = parse_qs(parsed.query or "", keep_blank_values=True)
        normalized_query = urlencode([(k, v) for k, vals in params.items() for v in vals], doseq=True)
        relative_src = f"{path}{'?' + normalized_query if normalized_query else ''}"

        content_id_match = re.match(r"^/web/content/(\d+)$", path)
        if content_id_match:
            attachment = request.env["ir.attachment"].browse(int(content_id_match.group(1))).exists()
            if not attachment:
                return None
            attachment.check("read")
            filename = attachment.name or (title or "")
            payload = base64.b64decode(attachment.datas or b"")
            preview_url = self._with_download_flag(relative_src, download=False)
            download_url = self._with_download_flag(relative_src, download=True)
            extension = self._extract_extension(filename, ext=ext)
            return {
                "filename": filename,
                "payload": payload,
                "preview_url": preview_url,
                "download_url": download_url,
                "extension": extension,
            }

        if path != "/web/content":
            return None
        model = (params.get("model") or [None])[0]
        rec_id = (params.get("id") or [None])[0]
        field = (params.get("field") or ["datas"])[0]
        if not model or not rec_id or not field:
            return None
        # Chỉ cho phép truy cập field binary an toàn
        ALLOWED_BINARY_FIELDS = {"datas", "image_1920", "image_1024", "image_512",
                                  "image_256", "image_128", "raw", "db_datas"}
        if field not in ALLOWED_BINARY_FIELDS:
            return None
        try:
            rec_id = int(rec_id)
        except (TypeError, ValueError):
            return None

        record = request.env[model].browse(rec_id).exists()
        if not record:
            return None
        record.check_access_rights("read")
        record.check_access_rule("read")

        binary_value = record[field]
        payload = base64.b64decode(binary_value or b"")

        filename_field = (params.get("filename_field") or [None])[0]
        filename = ""
        if filename_field and filename_field in record._fields:
            filename = record[filename_field] or ""
        filename = filename or title or ""

        preview_url = self._with_download_flag(relative_src, download=False)
        download_url = self._with_download_flag(relative_src, download=True)
        extension = self._extract_extension(filename, ext=ext)
        return {
            "filename": filename,
            "payload": payload,
            "preview_url": preview_url,
            "download_url": download_url,
            "extension": extension,
        }

    @staticmethod
    def _with_download_flag(url, download):
        parsed = urlparse(url)
        params = parse_qs(parsed.query or "", keep_blank_values=True)
        params["download"] = ["true" if download else "false"]
        query = urlencode([(k, v) for k, vals in params.items() for v in vals], doseq=True)
        return f"{parsed.path}?{query}" if query else parsed.path

    @staticmethod
    def _extract_extension(filename, ext=None):
        if filename and "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        if ext:
            return str(ext).lower().strip(".")
        guessed, _ = mimetypes.guess_type(filename or "")
        return mimetypes.guess_extension(guessed).lstrip(".") if guessed else ""

    def _shell(self, title, content, download_url):
        safe_title = html.escape(title or "Attachment Preview")
        safe_download = html.escape(download_url or "#")
        return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f3f4f6; color: #111827; }}
    .wrap {{ height: 100vh; display: flex; flex-direction: column; }}
    .head {{
      display: flex; justify-content: space-between; align-items: center;
      background: #111827; color: #fff; padding: 10px 14px;
    }}
    .title {{ font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .btn {{
      color: #fff; text-decoration: none; border: 1px solid #4b5563;
      padding: 6px 10px; border-radius: 6px; background: #1f2937; font-size: 13px;
    }}
    .content {{ flex: 1; overflow: auto; background: #fff; }}
    .pad {{ padding: 16px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f4f6; position: sticky; top: 0; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
    .note {{ color: #6b7280; font-size: 12px; margin-top: 8px; }}
    .sheet {{ margin-bottom: 22px; }}
    .sheet h3 {{ margin: 0 0 8px; font-size: 15px; }}
    p {{ margin: 0 0 10px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <div class="title">{safe_title}</div>
    </div>
    <div class="content">{content}</div>
  </div>
</body>
</html>"""

    def _render_pdf(self, preview_url):
        return f'<iframe src="{html.escape(preview_url)}" style="width:100%;height:100%;border:0;"></iframe>'

    def _render_image(self, preview_url, filename):
        return (
            '<div class="pad" style="height:100%;display:flex;justify-content:center;align-items:flex-start;">'
            f'<img src="{html.escape(preview_url)}" alt="{html.escape(filename or "image")}" '
            'style="max-width:100%;height:auto;object-fit:contain;">'
            "</div>"
        )

    def _render_viewerjs(self, preview_url, filename, extension):
        viewer_url = (
            "/attachment_preview/static/lib/ViewerJS/index.html"
            f"?type={quote(extension or '')}"
            f"&title={quote(filename or '')}"
            "&zoom=automatic"
            f"#{preview_url}"
        )
        return f'<iframe src="{viewer_url}" style="width:100%;height:100%;border:0;"></iframe>'

    def _render_text(self, payload, filename):
        text = payload.decode("utf-8", errors="replace")
        return f'<div class="pad"><pre>{html.escape(text)}</pre></div>'

    def _render_docx(self, payload, filename):
        try:
            import mammoth  # type: ignore

            result = mammoth.convert_to_html(io.BytesIO(payload))
            content = result.value or "<p>(Khong co noi dung)</p>"
            return f'<div class="pad">{content}</div>'
        except Exception:
            pass

        paragraphs = []
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                with zf.open("word/document.xml") as doc_xml:
                    root = ET.parse(doc_xml).getroot()
                for para in root.findall(".//w:p", DOCX_NS):
                    texts = [node.text or "" for node in para.findall(".//w:t", DOCX_NS)]
                    line = "".join(texts).strip()
                    if line:
                        paragraphs.append(line)
        except Exception:
            return self._render_unsupported(filename, "docx")

        items = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs[:3000]) or "<p>(Khong co noi dung)</p>"
        return f'<div class="pad">{items}<div class="note">Docx fallback mode.</div></div>'

    def _render_xlsx(self, payload, filename):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                shared_strings = self._xlsx_read_shared_strings(zf)
                sheet_names = self._xlsx_read_sheet_names(zf)
                sheet_tables = self._xlsx_read_sheet_tables(zf, shared_strings, sheet_names)
        except Exception:
            return self._render_unsupported(filename, "excel")

        if not sheet_tables:
            return '<div class="pad">(Khong co du lieu)</div>'

        body_parts = ['<div class="pad">']
        for sheet_name, rows, truncated in sheet_tables:
            body_parts.append(f'<div class="sheet"><h3>{html.escape(sheet_name)}</h3><table>')
            for ridx, row in enumerate(rows):
                tag = "th" if ridx == 0 else "td"
                body_parts.append("<tr>")
                for cell in row:
                    body_parts.append(f"<{tag}>{html.escape(cell)}</{tag}>")
                body_parts.append("</tr>")
            body_parts.append("</table>")
            if truncated:
                body_parts.append('<div class="note">Da rut gon toi da 300 dong.</div>')
            body_parts.append("</div>")
        body_parts.append("</div>")
        return "".join(body_parts)

    def _xlsx_read_shared_strings(self, zf):
        path = "xl/sharedStrings.xml"
        if path not in zf.namelist():
            return []
        with zf.open(path) as f:
            root = ET.parse(f).getroot()
        values = []
        for si in root.findall(f".//{{{XLSX_MAIN_NS}}}si"):
            texts = [t.text or "" for t in si.findall(f".//{{{XLSX_MAIN_NS}}}t")]
            values.append("".join(texts))
        return values

    def _xlsx_read_sheet_names(self, zf):
        rel_map = {}
        rel_path = "xl/_rels/workbook.xml.rels"
        if rel_path in zf.namelist():
            with zf.open(rel_path) as f:
                rel_root = ET.parse(f).getroot()
            for rel in rel_root.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target")
                if rid and target:
                    rel_map[rid] = target.replace("\\", "/").lstrip("/")

        names = {}
        with zf.open("xl/workbook.xml") as f:
            wb_root = ET.parse(f).getroot()
        for sheet in wb_root.findall(f".//{{{XLSX_MAIN_NS}}}sheet"):
            rid = sheet.attrib.get(f"{{{XLSX_REL_NS}}}id")
            name = sheet.attrib.get("name", "Sheet")
            target = rel_map.get(rid, "")
            if target and not target.startswith("xl/"):
                target = f"xl/{target}"
            names[target] = name
        return names

    def _xlsx_read_sheet_tables(self, zf, shared_strings, sheet_names):
        results = []
        sheet_paths = sorted(p for p in zf.namelist() if p.startswith("xl/worksheets/sheet") and p.endswith(".xml"))
        for sheet_path in sheet_paths:
            with zf.open(sheet_path) as f:
                root = ET.parse(f).getroot()

            all_rows = root.findall(f".//{{{XLSX_MAIN_NS}}}row")
            rows = []
            for row in all_rows[:300]:
                cells = []
                for cell in row.findall(f".//{{{XLSX_MAIN_NS}}}c"):
                    ctype = cell.attrib.get("t")
                    value_node = cell.find(f"./{{{XLSX_MAIN_NS}}}v")
                    inline_node = cell.find(f"./{{{XLSX_MAIN_NS}}}is/{{{XLSX_MAIN_NS}}}t")
                    raw_value = value_node.text if value_node is not None else ""
                    if ctype == "s" and raw_value:
                        try:
                            cells.append(shared_strings[int(raw_value)])
                        except Exception:
                            cells.append(raw_value)
                    elif inline_node is not None and inline_node.text:
                        cells.append(inline_node.text)
                    else:
                        cells.append(raw_value or "")
                rows.append(cells)

            if rows:
                max_cols = max(len(r) for r in rows)
                normalized = [r + [""] * (max_cols - len(r)) for r in rows]
            else:
                normalized = [[]]

            sheet_name = sheet_names.get(sheet_path, sheet_path.split("/")[-1])
            truncated = len(all_rows) > 300
            results.append((sheet_name, normalized, truncated))
        return results

    def _render_unsupported(self, filename, ext):
        return (
            '<div class="pad">'
            "<p>Dinh dang nay chua ho tro preview truc tiep.</p>"
            f"<p><b>File:</b> {html.escape(filename or '(khong ten)')}</p>"
            f"<p><b>Loai:</b> {html.escape(ext or 'unknown')}</p>"
            "</div>"
        )
