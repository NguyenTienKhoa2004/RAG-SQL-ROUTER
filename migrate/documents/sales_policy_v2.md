# Chính sách cửa hàng Forma Demo — phiên bản 2

Dữ liệu và chính sách giả lập để kiểm thử, không phải chính sách của cửa hàng thật.

## Giao hàng — đơn đặt từ 01/09/2026 đến hết 31/12/2026

Phiên bản 2 áp dụng theo ngày đặt đơn (`ordered_at`), không theo ngày giao hoặc ngày yêu cầu trả hàng. Không áp dụng hồi tố cho đơn tháng 8/2026.
Giá trị xét miễn phí giao hàng là tổng tiền hàng sau giảm giá: cộng `quantity * unit_price_vnd - discount_vnd` trên từng dòng hàng; không gồm phí giao hàng.
Vùng `remote` luôn thu 50.000 VND, kể cả khách VIP và đơn giá trị cao; ngoại lệ này được ưu tiên trước mọi điều kiện miễn phí.
Vùng `standard`: khách `vip` miễn phí; khách `regular` miễn phí khi giá trị xét đạt ít nhất 500.000 VND, dưới ngưỡng thu 30.000 VND.
Hạng khách dùng `membership_at_purchase` trên đơn hàng. Phí thực thu nằm ở `shipping_fee_vnd`, có thể bị thu sai và không phải bằng chứng của chính sách.

## Đổi trả — đơn đặt từ 01/09/2026 đến hết 31/12/2026

Phiên bản 2 áp dụng theo `ordered_at`. Hạn yêu cầu đổi trả là 30 ngày tính từ `delivered_at`, bao gồm ngày thứ 30; số ngày bằng ngày yêu cầu trừ ngày giao, ngày giao là ngày 0. Không áp dụng hồi tố cho đơn tháng 8/2026.
Đơn phải có trạng thái `delivered`. Thiếu ngày giao thì chưa thể kết luận đủ điều kiện về thời hạn.
Trong hạn: hàng lỗi (`defective`) được trả dù đã sử dụng hoặc là hàng thanh lý (`is_clearance = 1`).
Đổi ý (`change_of_mind`) chỉ được trả nếu hàng chưa sử dụng (`unused`), không thanh lý và thuộc nhóm `apparel` hoặc `home`. Nhóm `electronics` không được trả do đổi ý.
Ngoài hạn thì không được trả theo chính sách này. Thiếu tình trạng hàng khi xét đổi ý thì chưa đủ dữ kiện.
Tiền hoàn cho hàng đủ điều kiện được tính theo giá thực trả, phân bổ giảm giá dòng hàng đều theo số lượng; không hoàn phí giao hàng. Trạng thái yêu cầu trong SQL là lịch sử xử lý, không tự chứng minh yêu cầu đúng chính sách.
