# Kết quả Kaggle Pha 2C: P1 với C

**Phương án C đạt mục tiêu cấu trúc và cho cải thiện hiệu năng lặp lại được ở phần lớn cấu hình.** Trong transaction tạo booking, số SELECT giảm từ 6 xuống 1 mỗi booking, vì 5 SELECT vào `routes`, `locations` ×2, `vehicles` và `bus_operators` không còn chạy trong lúc giữ khóa Trip. CPU PostgreSQL trên mỗi booking giảm 14–27% ở mọi cấu hình, RPS thành công tăng 8–16%. Độ trễ cải thiện rõ ở tải tập trung với 20 users. Một số chỉ số p95 ở tải phân tán và một trường hợp p50 không cải thiện, chi tiết ở dưới. [Tổng hợp từng lượt](summary.csv) · [So sánh P1/C](comparison.csv).

## Điều kiện đo

- Hai bản được đo trong cùng phiên Kaggle CPU: AMD EPYC 7B12, 4 CPU logic, 31,3 GiB RAM, OpenJDK 21.0.12, PostgreSQL 16.15, Locust 2.32.10. Pha 1 dùng `fd6b5f3`, bản C dùng `a6c81ec`, chứa backend của `d15d161` và bộ đo [`load-tests/phase2/c`](../../../phase2/c/README.md). [SHA đầy đủ, hash JAR và cấu hình](manifest.json).
- JVM `-Xms256m -Xmx1024m`, Hikari pool 10, `READ COMMITTED`, `pg_stat_statements` bật từ đầu phiên. Locust `wait_time = 0`, số request đang xử lý bằng số users. Mỗi lượt khởi động backend trên DB khôi phục từ cùng snapshot Pha 1 và warm-up 100 booking trên chuyến riêng.
- Cả hai bản nhận cùng request **không có `Idempotency-Key`**. JAR C chứa cả B nhưng không dùng bảng key. B chỉ thêm 1 câu `SHOW TRANSACTION ISOLATION LEVEL` mỗi booking (nhóm `other`).
- Workload:
  - `legacy-distributed`: 1.000 ý định trên 1.000 chuyến × 4 ghế.
  - `distributed`: 4.000 ý định trên 100 chuyến × 40 ghế, trộn ngẫu nhiên.
  - `concentrated`: cùng 4.000 ý định, gom theo chuyến.
  - Mỗi workload chạy với 10 và 20 users, 3 lượt, đổi thứ tự P1/C giữa các lượt. Tổng cộng 36 lượt, 108.000 request trong cửa sổ đo, 0 lỗi. [Danh sách ý định phân tán](intents_distributed.json) · [Danh sách ý định tập trung](intents_concentrated.json).

## Đúng đắn

- Cả 36 lượt có `checked = True`: mỗi ý định đúng 1 booking CONFIRMED, quantity 1, giá 150.000. Mọi chuyến giữ `available_seats + ghế CONFIRMED = sức chứa`, không có ghế âm.
- Cả 18 cặp P1/C cho cùng kết quả theo ý định, cùng HTTP status (toàn bộ `201`) và cùng tập trường JSON. [Đối chiếu P1/C](equivalence.csv) · [Đối soát theo ý định, lượt mẫu](01_u20_concentrated_C/intent_results.csv).

## SQL trong transaction tạo booking

Số lượt thực thi mỗi booking là như nhau ở cả 3 lượt và mọi workload. Nguồn là chênh lệch `pg_stat_statements` của user ứng dụng trong cửa sổ đo.

| Nhóm SQL / booking | Pha 1 | Bản C |
|---|---:|---:|
| SELECT khóa `trips` (`FOR NO KEY UPDATE`) | 1 | 1 |
| SELECT quan hệ (`routes`, `locations` ×2, `vehicles`, `bus_operators`) | **5** | **0** |
| UPDATE `trips` trừ ghế, INSERT `bookings` | 2 | 2 |
| SELECT xác thực JWT (`users` + `roles`) | 1 | 1 |
| Khác (`BEGIN`, `BEGIN READ ONLY`; C có thêm `SHOW TRANSACTION ISOLATION LEVEL`) | 2 | 3 |
| **Tổng** | **11** | **7** |

Thời gian thực thi 5 SELECT quan hệ trên PostgreSQL chỉ khoảng 0,06 ms/booking. Lợi ích chính không nằm ở thời gian SQL phía DB. Nó nằm ở việc bớt 5 lượt round-trip JDBC và việc dựng entity Hibernate trong lúc đang giữ khóa dòng Trip. Ở tải tập trung, thời gian thực thi của câu SELECT khóa, phần lớn là thời gian chờ khóa, giảm từ 37,6 xuống 32,0 ms/booking (10 users) và từ 38,7 xuống 32,6 ms/booking (20 users). [SQL Pha 1](01_u20_concentrated_P1/sql.csv) · [SQL bản C](01_u20_concentrated_C/sql.csv).

## Độ trễ, thông lượng và tài nguyên

Mỗi ô ghi trung vị của ba lượt, kèm min–max trong ngoặc. Phần trăm thay đổi tính từ hai trung vị. **In đậm** là chỉ số mà khoảng min–max của hai bản không chồng nhau. [Bảng tổng hợp](aggregate.csv).

### Tải tập trung (`concentrated`, 4.000 booking)

| Chỉ số | 10 users · P1 | 10 users · C | Thay đổi | 20 users · P1 | 20 users · C | Thay đổi |
|---|---:|---:|---:|---:|---:|---:|
| p50 (ms) | 22,56 (22,40–23,57) | 27,41 (27,16–28,75) | **+21,5%** | 84,40 (83,41–84,90) | 71,92 (69,33–75,40) | **−14,8%** |
| p95 (ms) | 165,7 (165,0–168,0) | 127,5 (125,8–134,4) | **−23,0%** | 203,0 (202,1–206,0) | 178,1 (166,2–181,6) | **−12,3%** |
| RPS thành công | 204,7 (202,1–206,5) | 231,1 (218,8–231,8) | **+12,9%** | 205,6 (205,1–208,0) | 237,8 (229,6–249,1) | **+15,7%** |
| CPU Java (ms/booking) | 10,96 | 10,09 | **−7,9%** | 11,25 | 10,34 | **−8,0%** |
| CPU PostgreSQL (ms/booking) | 1,67 | 1,44 | **−13,8%** | 1,67 | 1,38 | **−17,5%** |
| Số backend chờ `Lock` trung bình | 7,70 | 7,42 | **−3,6%** | 8,11 | 7,67 | **−5,4%** |

### Tải phân tán (`distributed`, 4.000 booking)

| Chỉ số | 10 users · P1 | 10 users · C | Thay đổi | 20 users · P1 | 20 users · C | Thay đổi |
|---|---:|---:|---:|---:|---:|---:|
| p50 (ms) | 28,65 (28,13–28,87) | 25,68 (24,95–27,06) | **−10,4%** | 58,20 (52,57–59,25) | 51,61 (51,14–54,52) | −11,3% |
| p95 (ms) | 54,13 (53,84–57,22) | 51,83 (49,69–55,72) | −4,2% | 109,7 (108,8–119,9) | 106,3 (97,95–109,7) | −3,1% |
| RPS thành công | 318,8 (310,0–319,0) | 348,4 (325,2–358,3) | **+9,3%** | 307,1 (302,2–329,9) | 340,8 (322,7–345,3) | +11,0% |
| CPU Java (ms/booking) | 9,95 | 9,22 | **−7,3%** | 10,46 | 9,39 | −10,2% |
| CPU PostgreSQL (ms/booking) | 1,26 | 0,99 | **−21,3%** | 1,26 | 1,05 | **−17,2%** |
| Số backend chờ `Lock` trung bình | 0,10 | 0,07 | −25,9% | 0,25 | 0,17 | **−32,2%** |

### Tham chiếu fixture Pha 1 (`legacy-distributed`, 1.000 booking)

| Chỉ số | 10 users · P1 | 10 users · C | Thay đổi | 20 users · P1 | 20 users · C | Thay đổi |
|---|---:|---:|---:|---:|---:|---:|
| p95 (ms) | 70,08 (69,95–71,49) | 63,68 (58,26–65,98) | **−9,1%** | 135,1 (122,2–141,6) | 129,6 (125,8–133,7) | −4,0% |
| RPS thành công | 219,2 (214,7–223,3) | 249,6 (247,2–266,3) | **+13,9%** | 229,4 (225,2–251,0) | 247,3 (237,3–252,4) | +7,8% |
| CPU PostgreSQL (ms/booking) | 1,34 | 0,98 | **−26,9%** | 1,30 | 1,09 | **−16,2%** |

Không ghi nhận chờ khóa ở workload này vì mỗi chuyến chỉ nhận 1 request. RSS tối đa của Java nằm trong khoảng 534–628 MiB ở cả hai bản, không có khác biệt đáng kể.

## Diễn giải và giới hạn

- **Có thể kết luận:**
  - C loại bỏ toàn bộ truy vấn quan hệ khỏi transaction tạo booking (từ 11 xuống 7 SQL/booking).
  - C giảm CPU PostgreSQL mỗi booking ở mọi cấu hình.
  - Ở tải tập trung, C tăng RPS 13–16% và giảm p95 12–23%, lặp lại ở cả 3 lượt.
- **Chưa đủ để kết luận:**
  - p95 ở tải phân tán và các chỉ số 20 users của `legacy-distributed` có xu hướng giảm, nhưng khoảng min–max chồng nhau.
  - Ở tải tập trung 10 users, p50 của C **tăng** 21,5% trong khi p95 giảm 23% và RPS tăng. Có thể giải thích là khi giữ khóa ngắn hơn, hàng đợi trên cùng dòng Trip được xả đều hơn nên đuôi phân phối ngắn lại. Bài đo hiện tại chưa đủ dữ liệu để xác nhận cơ chế này. Cần xem phân phối đầy đủ trong `requests.csv` trước khi đưa vào báo cáo.
- **Giới hạn đo:**
  - Locust, Java và PostgreSQL chạy chung 4 CPU logic. CPU là thời gian CPU của tiến trình, chưa chia số CPU.
  - Chờ khóa là số backend đang chờ trong các mẫu lấy mỗi 0,2 giây, không phải thời gian chờ.
  - Thời gian thực thi câu SELECT khóa gồm cả thời gian chờ khóa và thời gian thực thi.
  - Ba lượt không bảo đảm ý nghĩa thống kê.
  - JAR C có thêm 1 SQL của B mỗi booking, khiến mức cải thiện của riêng C có thể bị đánh giá hơi thấp.
