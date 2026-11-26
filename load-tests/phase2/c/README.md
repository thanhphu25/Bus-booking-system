# Đối chứng Pha 2C trên Kaggle CPU: P1 với C

So Pha 1 tại `fd6b5f3026412d2359d70bfad681fc0773c8bcae` với bản Pha 2C (nhánh `feature/booking-trip-snapshot`) trên cùng một phiên Kaggle. Câu hỏi cần trả lời là C bỏ được công việc nào trong transaction tạo booking và việc đó ảnh hưởng thế nào tới p95, RPS, CPU và chờ khóa. [Kế hoạch Pha 2, mục 5](../../../docs/BusBooking_KeHoach_Pha2.md#5-t4c--đường-ghi-đặt-vé-chỉ-đọc-dữ-liệu-cần-thiết).

## Thiết kế bài đo

- **Request giống nhau và không có `Idempotency-Key`.** Bản C được build từ nhánh tạo từ B, nên JAR C chứa cả B (migration V17). Khi không gửi key, cả hai bản đi qua cùng use case tạo booking. Trên đường này, khác biệt còn lại so với P1 là snapshot Trip của C và một câu `SHOW TRANSACTION ISOLATION LEVEL` do `@Transactional(isolation = READ_COMMITTED)` của B sinh ra. Câu này hiện ở nhóm `other` trong `sql.csv`.
- **Fixture** ([fixture.sql](fixture.sql)), nạp một lần vào snapshot Pha 1 (V1–V16) rồi khôi phục cho từng lượt:
  - 1.000 chuyến × 4 ghế: tham chiếu theo bài POST cũ của Pha 1.
  - 100 chuyến × 40 ghế: fixture chính.
  - 10 chuyến × 40 ghế: chỉ dùng cho warm-up, không tiêu ghế của chuyến được đo.
  - 4 tài khoản USER. JWT được lấy trước khoảng đo.
- **Workload** (cùng seed cho cả hai bản):

| Workload | Ý định | Thứ tự |
|---|---:|---|
| `legacy-distributed` | 1.000, mỗi chuyến 4 ghế nhận 1 ý định | Trộn ngẫu nhiên |
| `distributed` | 4.000, mỗi chuyến 40 ghế nhận đúng 40 ý định | Trộn ngẫu nhiên trên 100 chuyến |
| `concentrated` | Cùng 4.000 ý định | Gom theo chuyến, các request đang xử lý tranh cùng một dòng Trip |

- **Tải:** Locust `wait_time = 0`, chạy 10 và 20 users, số request đang xử lý không vượt quá số users. Mỗi lượt phát hết danh sách ý định rồi mới dừng. Có 3 lượt, đổi thứ tự P1/C giữa các lượt. Mỗi lượt khởi động lại backend trên DB sạch và warm-up 100 booking.
- **Cấu hình cố định:** Java 21, `-Xms256m -Xmx1024m`, Hikari pool 10, PostgreSQL bật `pg_stat_statements` từ đầu phiên.

## Chạy notebook

1. Push nhánh có thư mục này. Import [notebook](busbooking-phase2-c-kaggle.ipynb), chọn **Accelerator: None** và bật **Internet**.
2. Ở cell đầu, `C_SHA = None` nghĩa là lấy commit mới nhất của `C_BRANCH`. Với lượt đo chính thức, ghim SHA 40 ký tự. `USERS` và `REPETITIONS` có thể giảm để chạy thử nhanh.
3. Chạy tất cả cell trong một phiên. Notebook build hai JAR từ hai checkout sạch, lấy `benchmark.py`, `locustfile.py` và `fixture.sql` từ checkout C, rồi chạy. Mặc định có 36 lượt. Khi xong, tải `phase2-c-*.zip` trong **Output** và lưu vào `load-tests/results/phase2/<run_id>/`.

Chạy local (cần PostgreSQL có `shared_preload_libraries=pg_stat_statements`, mật khẩu superuser `postgres` trong `PHASE2_PG_PASSWORD`, và cổng 8085 còn trống):

```bash
PHASE2_PG_PASSWORD=... python load-tests/phase2/c/benchmark.py --java "$JAVA_HOME/bin/java" --pg-port 55434 --pg-pid <PID postmaster> --p1-jar busbooking-p1.jar --c-jar busbooking-c.jar --c-sha <SHA C> --output out --users 10 --repetitions 1
```

Kết quả chính thức đầu tiên: [phase2-c-20261126T010717Z](../../results/phase2/phase2-c-20261126T010717Z/README.md).

## Đọc kết quả

| File | Nội dung |
|---|---|
| `summary.csv` | Một dòng cho mỗi lượt: p50/p95, RPS thành công, SQL/booking, CPU s/booking, RSS, chờ khóa, `checked` |
| `aggregate.csv` | Trung vị và min–max theo bản × workload × users |
| `comparison.csv` | P1 với C theo từng chỉ số: trung vị, min–max, `change_pct`, `ranges_overlap` |
| `equivalence.csv` | P1 và C cho cùng kết quả theo ý định (chuyến, quantity, giá, trạng thái), cùng HTTP status và cùng tập trường JSON |
| `<lượt>/sql.csv` | Chênh lệch `pg_stat_statements` của user ứng dụng trong khoảng đo, phân nhóm `auth`, `relation_select`, `trip_lock_select`, `trip_seat_update`, `booking_insert`, `other` |
| `<lượt>/locks.csv` | Mẫu `pg_stat_activity` mỗi 0,2 giây: số backend đang chạy và số backend chờ `Lock` |
| `<lượt>/resources.csv` | CPU tích lũy và RSS của Java, PostgreSQL (gồm tiến trình con) và Locust |
| `<lượt>/bookings.csv`, `seats.csv`, `intent_results.csv` | Đối soát booking và ghế theo ý định |

Cách đọc:

- **Bằng chứng cấu trúc:**
  - `relation_select_per_booking`: P1 dự kiến là 5 (`routes`, `locations` ×2, `vehicles`, `bus_operators`), C phải là 0.
  - `booking_select_per_booking`: các SELECT trong use case, không tính SQL xác thực.
  - SQL xác thực (`auth_sql_per_booking`) giống nhau ở hai bản và được báo riêng.
- **Hiệu năng:**
  - Chỉ nhận là cải thiện khi xu hướng lặp lại ở cả 3 lượt và khoảng min–max của hai bản không chồng nhau (`ranges_overlap = False`).
  - Trung vị p95 theo lượt không phải p95 gộp của mọi request.
  - Nếu SQL giảm nhưng p95/RPS nằm trong dao động thì chỉ ghi là cải thiện hiệu quả truy cập dữ liệu.
- **Chờ khóa:**
  - `fraction_samples_with_lock_wait` và `mean_lock_waiting` là tỷ lệ mẫu đang chờ, không phải thời gian chờ khóa.
  - Kỳ vọng thấy chờ khóa chủ yếu ở `concentrated`.
- **Đúng đắn:**
  - Mọi lượt phải có `checked = True`: mỗi ý định đúng 1 booking CONFIRMED, quantity 1, giá 150.000, và `available_seats + ghế CONFIRMED = sức chứa`.
  - Mọi dòng `equivalence.csv` phải `True`.
  - Script dừng ngay khi một lượt không đạt.
- **CPU:** CPU s/booking là chênh CPU giữa các mẫu trong khoảng đo chia cho số booking. Đây là CPU tiến trình, chưa chia số CPU logic. PostgreSQL tính cả tiến trình con; RSS có thể cộng trùng trang chia sẻ.
