/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";

// Disable Odoo 18's auto column-width logic. It maps the columns array onto
// the <th> elements by index, but the injected "#" <th> shifts every data
// column by one slot, so the magic widths get assigned to the wrong cells
// and the body visually slides relative to the header.
ListRenderer.useMagicColumnWidths = false;

// Account for the injected "#" cell so that <td colspan="nbCols"> (empty rows)
// and the group-name <th colspan="..."> span the full table width including
// the new column.
patch(ListRenderer.prototype, {
    get nbCols() {
        return super.nbCols + 1;
    },
    getGroupNameCellColSpan(group) {
        return super.getGroupNameCellColSpan(group) + 1;
    },
});
