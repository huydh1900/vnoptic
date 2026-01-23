# -*- coding: utf-8 -*-
"""
Excel Template Generator for Product Import

Generates professional Excel templates for:
- Lens products (Mắt)
- Optical products (Gọng/Kính)
- Accessory products (Phụ kiện)

Uses xlsxwriter for creating styled Excel files.
"""

import io
from datetime import datetime

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

# Color scheme matching frontend design
COLORS = {
    'primary': '#2E5BBA',       # Blue primary
    'secondary': '#4A90E2',     # Light blue
    'warning': '#F5A623',       # Yellow warning
    'success': '#388E3C',       # Green success
    'light': '#F8F9FA',         # Light gray
    'white': '#FFFFFF',         # White
    'text': '#2C3E50',          # Dark gray for text
    'border': '#E1E8ED',        # Light border
    'header_bg': '#34495E',     # Dark gray header
    
    # 3 main colors for header fields
    'manual_input': '#4A90E2',  # Blue - Manual input
    'code_rule': '#F5A623',     # Yellow - Code rule
    'multi_code': '#388E3C',    # Green - Multi code
}

# Company info
COMPANY_NAME = 'CÔNG TY TNHH CÔNG NGHỆ QUANG HỌC VIỆT NAM'
COMPANY_ADDRESS = 'Số 63 phố Lê Duẩn, Phường Cửa Nam, Quận Hoàn Kiếm, Thành phố Hà Nội, Việt Nam'


class ExcelTemplateGenerator:
    """Generate Excel templates for product import"""
    
    def __init__(self):
        if xlsxwriter is None:
            raise ImportError("xlsxwriter is required. Install with: pip install xlsxwriter")
    
    def _create_workbook(self, output):
        """Create workbook with common formats"""
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Define common formats
        formats = {
            'company_header': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 14,
                'bold': True,
                'font_color': COLORS['primary'],
                'bg_color': COLORS['light'],
                'align': 'center',
                'valign': 'vcenter',
                'bottom': 2,
                'bottom_color': COLORS['primary'],
            }),
            'address': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 10,
                'italic': True,
                'font_color': COLORS['text'],
                'bg_color': COLORS['light'],
                'align': 'center',
                'valign': 'vcenter',
            }),
            'title': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 18,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['primary'],
                'align': 'center',
                'valign': 'vcenter',
                'border': 2,
                'border_color': COLORS['primary'],
            }),
            'instruction_blue': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 12,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['manual_input'],
                'align': 'left',
                'valign': 'vcenter',
                'border': 1,
                'border_color': COLORS['border'],
            }),
            'instruction_yellow': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 12,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['code_rule'],
                'align': 'left',
                'valign': 'vcenter',
                'border': 1,
                'border_color': COLORS['border'],
            }),
            'instruction_green': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 12,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['multi_code'],
                'align': 'left',
                'valign': 'vcenter',
                'border': 1,
                'border_color': COLORS['border'],
            }),
            'type_label': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 12,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['header_bg'],
                'align': 'right',
                'valign': 'vcenter',
            }),
            'type_value': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 12,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['header_bg'],
                'align': 'left',
                'valign': 'vcenter',
            }),
            'header_vi': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 11,
                'bold': True,
                'font_color': COLORS['text'],
                'bg_color': COLORS['warning'],
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'top': 2,
                'top_color': COLORS['primary'],
                'left': 1,
                'left_color': COLORS['border'],
                'right': 1,
                'right_color': COLORS['border'],
                'bottom': 1,
                'bottom_color': COLORS['border'],
            }),
            'header_en_blue': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 10,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['manual_input'],
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'border': 1,
                'border_color': COLORS['border'],
                'bottom': 2,
                'bottom_color': COLORS['primary'],
            }),
            'header_en_yellow': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 10,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['code_rule'],
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'border': 1,
                'border_color': COLORS['border'],
                'bottom': 2,
                'bottom_color': COLORS['primary'],
            }),
            'header_en_green': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 10,
                'bold': True,
                'font_color': COLORS['white'],
                'bg_color': COLORS['multi_code'],
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'border': 1,
                'border_color': COLORS['border'],
                'bottom': 2,
                'bottom_color': COLORS['primary'],
            }),
            'data_odd': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 10,
                'font_color': COLORS['text'],
                'valign': 'vcenter',
                'text_wrap': True,
                'border': 1,
                'border_color': COLORS['border'],
            }),
            'data_even': workbook.add_format({
                'font_name': 'Segoe UI',
                'font_size': 10,
                'font_color': COLORS['text'],
                'bg_color': COLORS['light'],
                'valign': 'vcenter',
                'text_wrap': True,
                'border': 1,
                'border_color': COLORS['border'],
            }),
            'logo_area': workbook.add_format({
                'bg_color': COLORS['white'],
                'border': 2,
                'border_color': COLORS['primary'],
            }),
        }
        
        return workbook, formats
    
    def _setup_common_header(self, worksheet, formats, title, product_type_label):
        """Setup common header section for all templates"""
        # Row heights
        worksheet.set_row(0, 30)  # Company name
        worksheet.set_row(1, 22)  # Address
        worksheet.set_row(2, 35)  # Title
        worksheet.set_row(5, 22)  # Instruction 1
        worksheet.set_row(6, 22)  # Instruction 2
        worksheet.set_row(7, 22)  # Instruction 3 + Type
        worksheet.set_row(8, 25)  # Headers VI
        worksheet.set_row(9, 25)  # Headers EN
        
        # Company header
        worksheet.merge_range('A1:C1', COMPANY_NAME, formats['company_header'])
        
        # Address
        worksheet.merge_range('A2:C2', COMPANY_ADDRESS, formats['address'])
        
        # Title
        worksheet.merge_range('D3:L3', title, formats['title'])
        
        # Logo area
        worksheet.merge_range('A3:C8', '', formats['logo_area'])
        
        # Instructions
        worksheet.write('G6', '🔵 Tự nhập tay', formats['instruction_blue'])
        worksheet.write('G7', '🟡 Mã tự quy định', formats['instruction_yellow'])
        worksheet.write('G8', '🟢 Mã tự quy định, nhiều', formats['instruction_green'])
        
        # Product type
        worksheet.write('D8', 'LOẠI HÀNG:', formats['type_label'])
        worksheet.write('E8', product_type_label, formats['type_value'])
    
    def _write_headers(self, worksheet, formats, headers_vi, headers_en, col_widths, field_types):
        """Write header rows with appropriate colors"""
        # Write Vietnamese headers (row 9, index 8)
        for col, header in enumerate(headers_vi):
            worksheet.write(8, col, header, formats['header_vi'])
            worksheet.set_column(col, col, col_widths.get(col, 15))
        
        # Write English headers (row 10, index 9) with color coding
        for col, header in enumerate(headers_en):
            field_type = field_types.get(header, 'manual')
            if field_type == 'code':
                fmt = formats['header_en_yellow']
            elif field_type == 'multi':
                fmt = formats['header_en_green']
            else:
                fmt = formats['header_en_blue']
            worksheet.write(9, col, header, fmt)
    
    def _write_data_rows(self, worksheet, formats, num_cols, start_row=10, num_rows=100):
        """Write empty data rows with alternating colors"""
        for row in range(start_row, start_row + num_rows):
            worksheet.set_row(row, 35)
            for col in range(num_cols):
                fmt = formats['data_even'] if row % 2 == 0 else formats['data_odd']
                worksheet.write(row, col, '', fmt)
    
    def generate_lens_template(self):
        """Generate Lens product import template"""
        output = io.BytesIO()
        workbook, formats = self._create_workbook(output)
        worksheet = workbook.add_worksheet('Sheet1')
        
        # Setup header
        self._setup_common_header(worksheet, formats, 'BẢNG NHẬP HÀNG MẮT', 'Mắt')
        
        # Headers
        headers_vi = [
            'Nhóm', 'Ảnh', 'Tên đầy đủ', 'Tên tiếng Anh', 'Tên thương mại', 'Đơn vị', 
            'Thương hiệu', 'Nhà cung cấp', 'Quốc gia', 'Độ cầu', 'Độ trụ', 'Độ cộng thêm',
            'Trục', 'Lăng kính', 'Đáy lăng kính', 'Độ cong kính', 'Chỉ số tán sắc', 
            'Phân cực', 'Đường kính', 'Thiết kế 1', 'Thiết kế 2', 'Chất liệu', 'Chiết suất',
            'Chống UV', 'Lớp phủ', 'Ánh mạ', 'Đổi màu', 'Mạ màu', 'Độ đậm màu', 'Corridor',
            'Phủ gương', 'Bảo hành NCC', 'Bảo hành', 'Bảo hành bán lẻ', 'Phụ kiện',
            'Giá gốc', 'Loại tiền tệ', 'Giá nhập kho', 'Giá bán lẻ', 'Giá bán buôn theo %',
            'Giá buôn tối đa', 'Giá bán buôn tối thiểu', 'Công dụng', 'Hướng dẫn',
            'Cảnh báo', 'Bảo quản', 'Mô tả', 'Ghi chú',
        ]
        
        headers_en = [
            'Group', 'Image', 'FullName', 'EngName', 'TradeName', 'Unit', 'TradeMark',
            'Supplier', 'Country', 'SPH', 'CYL', 'ADD', 'AXIS', 'PRISM', 'PRISMBASE',
            'BASE', 'Abbe', 'Polarized', 'Diameter', 'Design1', 'Design2', 'Material',
            'Index', 'Uv', 'Coating', 'HMC', 'PHO', 'TIND', 'ColorInt', 'Corridor',
            'MirCoating', 'Supplier_Warranty', 'Warranty', 'Warranty_Retail', 'Accessory',
            'Origin_Price', 'Currency', 'Cost_Price', 'Retail_Price', 'Wholesale_Price',
            'Wholesale_Price_Max', 'Wholesale_Price_Min', 'Use', 'Guide', 'Warning',
            'Preserve', 'Description', 'Note',
        ]
        
        # Field types for color coding
        field_types = {
            # Manual input (blue)
            'Image': 'manual', 'FullName': 'manual', 'EngName': 'manual', 
            'TradeName': 'manual', 'Unit': 'manual', 'Origin_Price': 'manual',
            'Description': 'manual', 'Note': 'manual', 'Cost_Price': 'manual',
            'Retail_Price': 'manual', 'Wholesale_Price': 'manual',
            'Wholesale_Price_Max': 'manual', 'Wholesale_Price_Min': 'manual',
            
            # Code rule (yellow)
            'TradeMark': 'code', 'Supplier': 'code', 'Country': 'code', 'Group': 'code',
            'Design1': 'code', 'Design2': 'code', 'Material': 'code', 'Index': 'code',
            'Uv': 'code', 'HMC': 'code', 'PHO': 'code', 'TIND': 'code', 
            'Warranty': 'code', 'Warranty_Retail': 'code', 'Supplier_Warranty': 'code',
            'Currency': 'code',
            
            # Multi code (green)
            'Coating': 'multi', 'Accessory': 'multi',
        }
        
        # Column widths
        col_widths = {
            0: 12, 1: 15, 2: 25, 3: 22, 4: 18, 5: 8, 6: 18, 7: 20, 8: 12,
            9: 10, 10: 10, 11: 15, 12: 10, 13: 15, 14: 15, 15: 15, 16: 15,
            17: 15, 18: 15, 19: 14, 20: 14, 21: 14, 22: 14, 23: 12, 24: 14,
            25: 14, 26: 14, 27: 14, 28: 15, 29: 12, 30: 14, 31: 17, 32: 12,
            33: 17, 34: 16, 35: 12, 36: 16, 37: 15, 38: 12, 39: 20, 40: 17,
            41: 20, 42: 16, 43: 16, 44: 16, 45: 16, 46: 25, 47: 25,
        }
        
        self._write_headers(worksheet, formats, headers_vi, headers_en, col_widths, field_types)
        self._write_data_rows(worksheet, formats, len(headers_en))
        
        # Freeze panes
        worksheet.freeze_panes(10, 3)
        
        workbook.close()
        output.seek(0)
        return output.getvalue()
    
    def generate_opt_template(self):
        """Generate Optical product (Gọng/Kính) import template"""
        output = io.BytesIO()
        workbook, formats = self._create_workbook(output)
        worksheet = workbook.add_worksheet('Sheet1')
        
        # Setup header
        self._setup_common_header(worksheet, formats, 'BẢNG NHẬP HÀNG GỌNG / KÍNH', 'Gọng')
        
        # Gender instructions
        gender_fmt = workbook.add_format({
            'font_name': 'Segoe UI', 'font_size': 11, 'bold': True,
            'font_color': COLORS['text'], 'align': 'left', 'valign': 'vcenter',
        })
        worksheet.write('Q6', '0 - Nam', gender_fmt)
        worksheet.write('Q7', '1 - Nữ', gender_fmt)
        worksheet.write('Q8', '2 - Unisex', gender_fmt)
        
        headers_vi = [
            'Nhóm', 'Ảnh', 'Tên đầy đủ', 'Tên tiếng Anh', 'Tên thương mại', 'Đơn vị',
            'Thương hiệu', 'Nhà cung cấp', 'Quốc gia', 'Mã SKU', 'Mẫu', 'Mẫu NCC',
            'Serial', 'Mã màu', 'Mùa', 'Kiểu Gọng', 'Giới tính', 'Loại gọng', 'Hình dạng',
            'Ve', 'Càng kính', 'Chất liệu ve', 'Chất liệu chuôi càng', 'Chất liệu tròng',
            'Chất liệu mặt trước', 'Chất liệu càng', 'Màu tròng', 'Lớp phủ',
            'Màu mặt trước', 'Màu càng', 'Dài mắt', 'Cầu kính', 'Dài càng', 'Cao tròng',
            'Ngang mắt', 'Bảo hành NCC', 'Bảo hành', 'Bảo hành bán lẻ', 'Phụ kiện',
            'Giá gốc', 'Loại tiền tệ', 'Giá nhập kho', 'Giá bán lẻ', 'Giá bán buôn theo %',
            'Giá buôn tối đa', 'Giá bán buôn tối thiểu', 'Công dụng', 'Hướng dẫn',
            'Cảnh báo', 'Bảo quản', 'Mô tả', 'Ghi chú',
        ]
        
        headers_en = [
            'Group', 'Image', 'FullName', 'EngName', 'TradeName', 'Unit', 'TradeMark',
            'Supplier', 'Country', 'Sku', 'Model', 'Model_Supplier', 'Serial', 'Color_Code',
            'Season', 'Frame', 'Gender', 'Frame_Type', 'Shape', 'Ve', 'Temple',
            'Material_Ve', 'Material_TempleTip', 'Material_Lens', 'Material_Opt_Front',
            'Material_Opt_Temple', 'Color_Lens', 'Coating', 'Color_Opt_Front',
            'Color_Opt_Temple', 'Lens_Width', 'Bridge_Width', 'Temple_Width', 'Lens_Height',
            'Lens_Span', 'Supplier_Warranty', 'Warranty', 'Warranty_Retail', 'Accessory',
            'Origin_Price', 'Currency', 'Cost_Price', 'Retail_Price', 'Wholesale_Price',
            'Wholesale_Price_Max', 'Wholesale_Price_Min', 'Use', 'Guide', 'Warning',
            'Preserve', 'Description', 'Note',
        ]
        
        field_types = {
            # Manual input (blue)
            'Image': 'manual', 'FullName': 'manual', 'EngName': 'manual',
            'TradeName': 'manual', 'Unit': 'manual', 'Sku': 'manual', 'Serial': 'manual',
            'Season': 'manual', 'Lens_Width': 'manual', 'Bridge_Width': 'manual',
            'Temple_Width': 'manual', 'Lens_Height': 'manual', 'Lens_Span': 'manual',
            'Origin_Price': 'manual', 'Description': 'manual', 'Note': 'manual',
            
            # Code rule (yellow)
            'TradeMark': 'code', 'Supplier': 'code', 'Country': 'code', 'Frame': 'code',
            'Group': 'code', 'Frame_Type': 'code', 'Shape': 'code', 'Ve': 'code',
            'Temple': 'code', 'Material_Ve': 'code', 'Material_TempleTip': 'code',
            'Material_Lens': 'code', 'Supplier_Warranty': 'code', 'Color_Lens': 'code',
            'Warranty': 'code', 'Warranty_Retail': 'code', 'Currency': 'code',
            'Gender': 'code',
            
            # Multi code (green)
            'Material_Opt_Front': 'multi', 'Material_Opt_Temple': 'multi',
            'Coating': 'multi', 'Accessory': 'multi',
        }
        
        col_widths = {
            0: 12, 1: 15, 2: 25, 3: 22, 4: 18, 5: 8, 6: 18, 7: 20, 8: 12,
            9: 18, 10: 18, 11: 18, 12: 18, 13: 12, 14: 12, 15: 12, 16: 10,
            17: 12, 18: 12, 19: 8, 20: 17, 21: 16, 22: 16, 23: 16, 24: 21,
            25: 18, 26: 12, 27: 12, 28: 19, 29: 16, 30: 12, 31: 12, 32: 12,
            33: 12, 34: 12, 35: 16, 36: 12, 37: 16, 38: 16, 39: 12, 40: 16,
            41: 15, 42: 12, 43: 22, 44: 17, 45: 22, 46: 16, 47: 16, 48: 16,
            49: 16, 50: 25, 51: 25,
        }
        
        self._write_headers(worksheet, formats, headers_vi, headers_en, col_widths, field_types)
        self._write_data_rows(worksheet, formats, len(headers_en))
        
        worksheet.freeze_panes(10, 3)
        
        workbook.close()
        output.seek(0)
        return output.getvalue()
    
    def generate_accessory_template(self):
        """Generate Accessory product import template"""
        output = io.BytesIO()
        workbook, formats = self._create_workbook(output)
        worksheet = workbook.add_worksheet('Sheet1')
        
        # Setup header
        self._setup_common_header(worksheet, formats, 'BẢNG NHẬP HÀNG PHỤ KIỆN', 'Phụ kiện')
        
        headers_vi = [
            'Nhóm', 'Ảnh', 'Tên đầy đủ', 'Tên tiếng Anh', 'Tên thương mại', 'Đơn vị',
            'Thương hiệu', 'Nhà cung cấp', 'Quốc gia', 'Thiết kế', 'Hình dáng',
            'Chất liệu', 'Màu sắc', 'Chiều rộng', 'Chiều dài', 'Chiều cao', 'Đầu', 'Thân',
            'Bảo hành NCC', 'Bảo hành', 'Bảo hành bán lẻ', 'Phụ kiện', 'Giá gốc',
            'Loại tiền tệ', 'Giá nhập kho', 'Giá bán lẻ', 'Giá bán buôn theo %',
            'Giá buôn tối đa', 'Giá bán buôn tối thiểu', 'Công dụng', 'Hướng dẫn',
            'Cảnh báo', 'Bảo quản', 'Mô tả', 'Ghi chú',
        ]
        
        headers_en = [
            'Group', 'Image', 'FullName', 'EngName', 'TradeName', 'Unit', 'TradeMark',
            'Supplier', 'Country', 'Design', 'Shape', 'Material', 'Color', 'Width',
            'Length', 'Height', 'Head', 'Body', 'Supplier_Warranty', 'Warranty',
            'Warranty_Retail', 'Accessory', 'Origin_Price', 'Currency', 'Cost_Price',
            'Retail_Price', 'Wholesale_Price', 'Wholesale_Price_Max', 'Wholesale_Price_Min',
            'Use', 'Guide', 'Warning', 'Preserve', 'Description', 'Note',
        ]
        
        field_types = {
            # Manual input (blue)
            'Image': 'manual', 'FullName': 'manual', 'EngName': 'manual',
            'TradeName': 'manual', 'Unit': 'manual', 'Origin_Price': 'manual',
            'Description': 'manual', 'Note': 'manual',
            
            # Code rule (yellow)
            'TradeMark': 'code', 'Supplier': 'code', 'Country': 'code',
            'Supplier_Warranty': 'code', 'Warranty': 'code', 'Group': 'code',
            'Warranty_Retail': 'code', 'Currency': 'code', 'Design': 'code',
            'Shape': 'code', 'Material': 'code',
            
            # Multi code (green)
            'Accessory': 'multi',
        }
        
        col_widths = {
            0: 12, 1: 15, 2: 25, 3: 22, 4: 18, 5: 8, 6: 18, 7: 20, 8: 12,
            9: 16, 10: 16, 11: 16, 12: 16, 13: 12, 14: 12, 15: 12, 16: 12,
            17: 12, 18: 16, 19: 12, 20: 16, 21: 16, 22: 12, 23: 16, 24: 15,
            25: 12, 26: 22, 27: 17, 28: 22, 29: 16, 30: 16, 31: 16, 32: 16,
            33: 25, 34: 25,
        }
        
        self._write_headers(worksheet, formats, headers_vi, headers_en, col_widths, field_types)
        self._write_data_rows(worksheet, formats, len(headers_en))
        
        worksheet.freeze_panes(10, 3)
        
        workbook.close()
        output.seek(0)
        return output.getvalue()


def generate_lens_template():
    """Convenience function to generate lens template"""
    generator = ExcelTemplateGenerator()
    return generator.generate_lens_template()


def generate_opt_template():
    """Convenience function to generate optical template"""
    generator = ExcelTemplateGenerator()
    return generator.generate_opt_template()


def generate_accessory_template():
    """Convenience function to generate accessory template"""
    generator = ExcelTemplateGenerator()
    return generator.generate_accessory_template()
