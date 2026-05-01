# 📚 Tài liệu Hướng dẫn Sử dụng — VNOptic

> Bộ tài liệu hướng dẫn vận hành phần mềm VNOptic (Odoo 18) cho người dùng cuối.

## 📖 Danh sách tài liệu

| File | Đối tượng | Mô tả |
|---|---|---|
| [HUONG_DAN_BAN_LE_POS.md](./HUONG_DAN_BAN_LE_POS.md) | Nhân viên thu ngân tại quầy | Cách dùng POS bán mắt kính, nhập đơn kính (Rx), thanh toán, đóng phiên |
| [HUONG_DAN_BAN_BUON.md](./HUONG_DAN_BAN_BUON.md) | Sale phụ trách đại lý | Quy trình bán buôn từ báo giá đến công nợ, xử lý đơn cắt theo Rx |

## 🎯 Cách sử dụng tài liệu này

### Khi đi tư vấn khách hàng
- Mở 2 file `.md` trên IDE / VS Code có preview Markdown để show step-by-step
- In ra giấy / xuất PDF (`pandoc HUONG_DAN_*.md -o output.pdf`) để giao KH

### Khi training nhân viên cửa hàng
- Bắt đầu với **HUONG_DAN_BAN_LE_POS.md**
- Demo trực tiếp trên hệ thống test theo từng bước
- Phát checklist đầu/cuối ca cuối tài liệu cho NV

### Khi training sale bán buôn
- Bắt đầu với **HUONG_DAN_BAN_BUON.md**
- Yêu cầu sale tạo thử 1 đơn từ đại lý mẫu trên môi trường test
- Đặc biệt nhấn mạnh phần Rx (mục 5) cho ngành kính

## 🛠 Module Phase 1 đã triển khai

| Module | Vai trò |
|---|---|
| `vnop_sale_channel` | Phân kênh bán buôn / bán lẻ + bảng giá theo channel + Rx fields trên SO line |
| `vnop_promotion` | KM theo channel, 6 chương trình mẫu (khai trương, khách buôn, sinh viên, Black Friday...) |
| `vnop_pos_optical` | POS chuyên ngành kính: cấu hình quầy, payment methods VN, popup nhập Rx OWL |

## 📞 Liên hệ

- **Triển khai / kỹ thuật:** IT VNOptic
- **Nghiệp vụ bán hàng:** Phòng Kinh doanh
- **Đào tạo người dùng:** Trưởng phòng vận hành
