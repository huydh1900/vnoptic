/** @odoo-module **/

import { Component } from "@odoo/owl";

import { browser } from "@web/core/browser/browser";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";

const cogMenuRegistry = registry.category("cogMenu");

function isProductTemplateList(env) {
    const resModel = env.searchModel?.resModel || env.config?.resModel || env.model?.root?.resModel;
    return env.config?.viewType === "list" && resModel === "product.template";
}

function downloadTemplate(productType) {
    const params = new URLSearchParams({
        product_type: productType,
        file_format: "xlsx",
    });
    browser.location.href = `/vnop_sync/product_template_template_download?${params.toString()}`;
}

class ExportMatTemplateMenu extends Component {
    static template = "vnop_sync.ExportMatTemplateMenu";
    static components = { DropdownItem };

    onSelected() {
        downloadTemplate("lens");
    }
}

class ExportGongTemplateMenu extends Component {
    static template = "vnop_sync.ExportGongTemplateMenu";
    static components = { DropdownItem };

    onSelected() {
        downloadTemplate("frame");
    }
}

class ExportPhuKienTemplateMenu extends Component {
    static template = "vnop_sync.ExportPhuKienTemplateMenu";
    static components = { DropdownItem };

    onSelected() {
        downloadTemplate("accessory");
    }
}

const sharedConfig = {
    groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
    isDisplayed: (env) => isProductTemplateList(env),
};

cogMenuRegistry.add(
    "vnop-export-template-mat-menu",
    {
        ...sharedConfig,
        Component: ExportMatTemplateMenu,
    },
    { sequence: 11 }
);

cogMenuRegistry.add(
    "vnop-export-template-gong-menu",
    {
        ...sharedConfig,
        Component: ExportGongTemplateMenu,
    },
    { sequence: 12 }
);

cogMenuRegistry.add(
    "vnop-export-template-phukien-menu",
    {
        ...sharedConfig,
        Component: ExportPhuKienTemplateMenu,
    },
    { sequence: 13 }
);
