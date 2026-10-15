# Migration dữ liệu bán hàng

Bộ dữ liệu **giả lập**, tái tạo cố định bằng seed `20261014`, dùng SQLite và Python standard library; không cần API key hoặc Milvus để migrate.

## Chạy

Từ thư mục gốc dự án:

```powershell
.venv\Scripts\python.exe migrate/seed_sales.py
# Hoặc: uv run python migrate/seed_sales.py
```

Tạo `sales_database.sqlite` gồm **120 khách hàng, 12 sản phẩm, 608 đơn hàng** tháng 8–9/2026, chi tiết đơn, thanh toán và yêu cầu trả hàng. Script chạy lại không chèn trùng; từ chối ghi đè database khác hoặc phiên bản không hỗ trợ. Nếu lỗi khi tạo mới, transaction được rollback và file mới được dọn. Không sửa `city_database.sqlite`.

App mặc định dùng `sales_database.sqlite`. Nếu đã có `DATABASE_PATH` trong `.env` hoặc biến môi trường, đổi nó thành `sales_database.sqlite`. Khởi động lại backend và kết nối session mới sau khi đổi database.

Upload **cả hai file trong `migrate/documents/`** qua giao diện để bật RAG chính sách. Không upload README, benchmark hoặc schema làm tài liệu trả lời. Các tài liệu mẫu cửa hàng cũ trong `data/` thuộc bộ dữ liệu khác; nên bắt đầu session mới và chỉ upload chính sách tương ứng.

Để tạo bản thử nghiệm riêng:

```powershell
.venv\Scripts\python.exe migrate/seed_sales.py --database migrate/sales_experiment.sqlite
```

## Schema và quy ước

| Bảng | Nội dung |
| --- | --- |
| `customers` | Khách hàng; tên có thể trùng, dùng `customer_id` phân biệt |
| `products` | Danh mục, giá niêm yết hiện tại |
| `orders` | Ngày đặt/giao, trạng thái, vùng giao, hạng khách lúc mua, phí thực thu |
| `order_items` | Số lượng, giá tại thời điểm mua, giảm giá **toàn dòng**, cờ thanh lý |
| `payments` | Từng lần thanh toán; có lần thất bại và thanh toán chia đôi |
| `returns` | Yêu cầu trả theo dòng hàng; lý do, tình trạng hàng, số lượng, tiền/ngày thực hoàn |

- Tiền là số nguyên VND; ngày là `YYYY-MM-DD`. NULL là thiếu dữ liệu, không phải 0.
- Tiền hàng sau giảm giá = `SUM(quantity * unit_price_vnd - discount_vnd)`. Không dùng giá niêm yết để tính doanh thu lịch sử.
- Doanh thu thuần theo **nhóm đơn đặt trong kỳ**: tiền hàng của đơn `delivered` trừ tiền hoàn `refunded` gắn với các đơn đó, kể cả hoàn vào tháng sau; không tính phí giao hàng. Phải nêu mốc dữ liệu nếu người dùng yêu cầu báo cáo tại một thời điểm.
- Dòng tiền theo **ngày giao dịch**: tổng `payments.status = 'succeeded'` theo `paid_at` trừ tiền hoàn `returns.status = 'refunded'` theo `refunded_at`. Thanh toán gồm cả phí giao hàng. Đây là thước đo khác doanh thu thuần.
- Tổng hợp riêng từng bảng con trước khi JOIN để tránh nhân đôi tiền khi một đơn có nhiều dòng hàng, nhiều lần thanh toán hoặc nhiều yêu cầu trả.
- Đơn `cancelled` và `pending` không có thanh toán thành công trong bộ dữ liệu này. Đơn DH1005 đã giao nhưng bị thiếu ngày giao có chủ đích.
- Chính sách chỉ nằm trong tài liệu, không được mã hóa thành đáp án/điều kiện đủ chuẩn trong database. SQL cung cấp sự kiện, RAG cung cấp quy tắc.

## Câu hỏi và đáp án kiểm tra

| Câu hỏi | Tool cần | Đáp án mong đợi |
| --- | --- | --- |
| Có bao nhiêu đơn hàng? | SQL | 608 |
| KH001 và KH002 có phải một người vì cùng tên không? | SQL | Hai hồ sơ khác ID/email, cùng tên Nguyễn Văn An; không tự gộp |
| DH1004 đã thanh toán thành công bao nhiêu? | SQL | 690.000 VND: hai lần 345.000; bỏ lần thất bại 690.000 |
| Doanh thu thuần DH1004 sau tất cả khoản hoàn đã ghi nhận, không gồm giao hàng? | SQL | 510.000 VND = 690.000 − 180.000; không trừ toàn bộ dòng 3 áo |
| Dòng tiền DH1004 trong tháng 9 và tháng 10/2026? | SQL | Tháng 9: +690.000; tháng 10: −180.000 VND |
| Khách thường vùng standard được miễn giao hàng từ bao nhiêu trong tháng 8 và 9/2026? | RAG | Tháng 8: 700.000; tháng 9: 500.000 VND sau giảm giá |
| DH1001 và DH1002 có đủ điều kiện trả theo yêu cầu đã ghi không? | SQL + RAG | DH1001: không, 17 ngày > 14; DH1002: có, 17 ngày ≤ 30 |
| Đơn nào tháng 9 bị thu thừa phí giao hàng và cần hoàn bao nhiêu? | SQL + RAG | Chỉ DH1002, 30.000 VND; đây là khoản cần hoàn, chưa ghi nhận hoàn |
| DH1003 là VIP, sao vẫn mất phí? | SQL + RAG | Vùng remote ưu tiên ngoại lệ, phí 50.000 VND đúng |
| DH1005 có đủ điều kiện trả không? | SQL + RAG | Chưa đủ dữ kiện vì thiếu ngày giao |
| DH1006 và DH1007 cùng hàng thanh lý, có được trả không? | SQL + RAG | DH1006 đổi ý: không; DH1007 hàng lỗi trong hạn: có, 180.000 VND |
| DH1008 giá niêm yết 600.000, sao không miễn giao hàng? | SQL + RAG | Sau giảm giá còn 480.000 < 500.000, phí 30.000 VND đúng |

Chấm riêng việc chọn tool, kết quả SQL, phiên bản chính sách và nhận diện thiếu dữ kiện. Test tự động dùng mock LLM để kiểm tra đường chạy; chất lượng định tuyến/suy luận thực tế cần chạy với OpenRouter và Milvus.
