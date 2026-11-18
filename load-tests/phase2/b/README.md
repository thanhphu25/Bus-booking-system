# Đối chứng Pha 2B trên Kaggle CPU

Chạy Pha 1 tại `fd6b5f3026412d2359d70bfad681fc0773c8bcae` và bản chỉ có cải tiến B trên cùng một phiên Kaggle. Benchmark dùng 1.000 ý định mua một vé, bốn tài khoản USER giả lập và 20 Locust users, giới hạn 20 request đang xử lý, không thêm thời gian chờ. Cả hai bản nhận cùng key, payload và fixture. Mỗi workload chạy ba lượt đối chứng và đảo thứ tự P1/B giữa các lượt. [Kế hoạch Pha 2](../../../docs/BusBooking_KeHoach_Pha2.md#4-t4b--idempotency-bền-vững-cho-đặt-vé).

## Chạy notebook

1. Import notebook, chọn **Accelerator: None** và bật **Internet**. [Notebook Kaggle](busbooking-phase2-b-kaggle.ipynb).
2. Chạy tất cả cell trong một phiên. Notebook clone GitHub, dùng Java 21 và Maven Wrapper để build Pha 1 và B từ hai checkout sạch. Hai SHA đã được điền sẵn, trong đó B là `ea951289b62e23843ef6ce2033acd6df16844f50`.
3. Notebook lấy `benchmark.py` và `fixture.sql` từ checkout B, nạp fixture vào snapshot Pha 1 trong PostgreSQL riêng rồi khôi phục snapshot cho mỗi lượt. Mỗi bản chạy Flyway theo JAR rồi warm-up trên 100 chuyến riêng. Tải file `phase2-b-*.zip` từ **Output** khi hoàn tất.

## Đọc kết quả

| Workload | Request mỗi bản | Kết quả nghiệm thu nếu mọi request thành công |
|---|---:|---|
| `first-only` | 1.000 | Mỗi bản có 1.000 booking và trừ 1.000 ghế. So p95 lần đầu, RPS và SQL để định lượng chi phí bổ sung của B. |
| `retry` | 1.200 | P1 dự kiến có 1.200 booking và trừ 1.200 ghế. B phải có 1.000 booking, trừ 1.000 ghế và trả 200 cho 200 lần đọc lại. Lấy số chính thức từ DB và log của từng lượt. |

- `summary.csv` chứa số liệu từng lượt. `aggregate.csv` chứa trung vị và min–max của p95 theo lượt và RPS thành công. `requests.csv` chứa từng request. Với cặp đồng thời, lần gửi được gắn nhãn `retry` có thể giành key và trả 201. `replayed_200` đo riêng các response đọc lại thực sự.
- `intent_results.csv`, `bookings.csv`, `seats.csv` và `keys.csv` đối soát theo mã ý định. Mỗi chuyến có bốn ghế nên cả hai lần gửi của P1 đều đủ ghế. `overlapping_pairs` ghi số cặp có hai khoảng request chồng nhau tại Locust.
- `sql.csv` lấy chênh lệch `pg_stat_statements` theo database và user ứng dụng sau warm-up. `resources.csv` giữ mẫu CPU tích lũy và RSS của Java, PostgreSQL và Locust. `metrics.json` tính chênh CPU giữa các mẫu trong cửa sổ đo, RSS của PostgreSQL là tổng RSS các tiến trình và có thể cộng trùng trang chia sẻ. `manifest.json` ghi cấu hình, SHA nguồn được kiểm tra khi checkout, hash JAR/script/fixture và hash danh sách ý định.
