# Kết quả Kaggle Pha 2B

**Phương án B đạt mục tiêu chống đặt trùng.** Trong cả ba lượt retry, bản B giảm số booking trùng và số ghế bị trừ thừa từ 200 mỗi lượt về 0. Đánh đổi ở luồng tạo mới là p95 tăng 13,91 ms và PostgreSQL thực thi thêm ba lệnh mỗi request. [Tổng hợp từng lượt](summary.csv).

## Điều kiện đo

- Hai bản được đo trong cùng phiên Kaggle CPU với Intel Xeon 2,20 GHz, 4 CPU logic, Java 21, PostgreSQL 16.15 và Locust 2.32.10. Pha 1 dùng `fd6b5f3`, bản B dùng `b2734bb`, chứa backend của `ea95128`. [SHA đầy đủ, hash artifact và cấu hình](manifest.json).
- Mỗi lượt dùng 20 Locust users, tối đa 20 request đang xử lý và 100 chuyến riêng cho warm-up. Fixture đo chung có 1.000 chuyến, bốn ghế mỗi chuyến và bốn USER giả lập. Cả hai bản gửi cùng `Idempotency-Key` theo danh sách ý định đã ghim.
- Có hai workload, mỗi workload chạy ba lượt cho mỗi bản. Tổng cộng 12 lượt, 13.200 request trong cửa sổ đo và 0 lỗi. PostgreSQL giữ đúng cân bằng ghế ở tất cả các chuyến đo. [Danh sách ý định không retry](intents_first-only.json) · [Danh sách ý định có retry](intents_retry.json).

## Đối soát booking và ghế

Mỗi lượt retry gồm 1.000 ý định mua một vé và thêm 200 request, chia đều giữa retry tuần tự và cặp gửi đồng thời. Log Locust cho thấy cả 100 cặp đồng thời có khoảng xử lý chồng nhau trong từng lượt. Đối soát xác nhận hai request của mỗi cặp trên bản B nhận cùng ID booking.

| Chỉ số mỗi lượt retry | Pha 1 | Bản B |
|---|---:|---:|
| Ý định mua thành công | 1.000 | 1.000 |
| Booking tạo mới | 1.200 | 1.000 |
| Booking trùng | 200 | **0** |
| Ghế bị trừ | 1.200 | 1.000 |
| Ghế bị trừ thừa | 200 | **0** |
| Phản hồi HTTP `201` / HTTP `200` | 1.200 / 0 | 1.000 / 200 |

Trong workload không retry, mỗi bản tạo đúng 1.000 booking và trừ 1.000 ghế mỗi lượt. [Đối soát theo ý định của Pha 1](01_retry_P1/intent_results.csv) · [Đối soát theo ý định của bản B](01_retry_B/intent_results.csv).

## Độ trễ, thông lượng và chi phí SQL

Mỗi ô độ trễ và RPS ghi trung vị của ba lượt, kèm min–max trong ngoặc. Phần trăm thay đổi được tính từ hai trung vị. [Bảng tổng hợp](aggregate.csv) · [Số liệu từng lượt](summary.csv).

| Chỉ số | Pha 1 | Bản B | Thay đổi |
|---|---:|---:|---:|
| Không retry · p95 tạo vé (ms) | 209,01 (205,13–211,44) | 222,92 (213,13–224,77) | +6,7% |
| Không retry · RPS | 145,02 (144,69–151,10) | 141,48 (137,75–142,14) | −2,4% |
| Không retry · lượt thực thi SQL / 1.000 request | 11.000 | 14.000 | +27,3% |
| Có retry · p95 của request gắn nhãn gửi lại (ms) | 206,94 (178,55–210,57) | 178,47 (165,09–185,76) | −13,8% |
| Có retry · RPS | 149,83 (148,87–171,49) | 151,59 (150,01–155,33) | +1,2% |
| Có retry · lượt thực thi SQL / 1.200 request | 13.200 | 15.400 | +16,7% |

`pg_stat_statements` ghi nhận ba lệnh bổ sung trên đường tạo mới ở bản B, gồm insert giành key, update gắn booking với key và `SHOW TRANSACTION ISOLATION LEVEL`. Với workload retry, bản B thực hiện 1.000 lượt khóa Trip, 1.000 lượt insert booking và 1.000 lượt trừ ghế. Mỗi số tương ứng ở Pha 1 là 1.200. [SQL Pha 1](01_retry_P1/sql.csv) · [SQL bản B](01_retry_B/sql.csv).

Khi gửi đồng thời, một request gắn nhãn `first` cũng có thể nhận `200` nếu request còn lại giành được key trước. Xét riêng phản hồi `200` của bản B, trung vị p95 là **182,94 ms** (179,15–192,79 ms). Theo cách gửi, trung vị p95 của HTTP `200` là 146,28 ms với retry tuần tự và 204,15 ms với cặp đồng thời. RPS ở workload retry tăng trong hai lượt và giảm trong một lượt. Kết luận về hiệu năng giới hạn ở tải và tỷ lệ retry đã đo. [Log request mẫu của bản B](01_retry_B/requests.csv).
