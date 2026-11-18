# Báo cáo Xác minh Kiểm thử tải Baseline (Lượt chạy lại)

**Mục đích:** Chạy lại kiểm thử tải độc lập trên Kaggle CPU để đối chứng, xác minh tính chính xác và khả năng tái lập (*reproducibility*) của số liệu baseline Pha 1 đã lưu trong repository trước khi bắt đầu cải tiến Pha 2.

---

## 1. Môi trường thực thi

Toàn bộ mã nguồn được `git clone` trực tiếp từ GitHub về Kaggle, build JAR bằng Java 21 và chạy độc lập theo đúng quy trình kiểm thử tải:

* **Môi trường:** Kaggle Notebook (CPU, không GPU, Internet: On).
* **Phần cứng:** 4 vCPU, **AMD EPYC 7B12**, 31.35 GB RAM *(phiên gốc trong repo chạy trên Intel Xeon 2.20GHz)*.
* **Phần mềm:** OpenJDK 21.0.13.1, PostgreSQL 16.15, Locust 2.47.0, Python 3.13.18.

---

## 2. Kết quả đối chiếu với Baseline gốc

### Kịch bản 1: Đọc chuyến xe (GET Trip) - 20 Virtual Users, 60 giây

| Chỉ số | Baseline Gốc (Repo) | Lượt Chạy Lại (Rerun) | Chênh lệch (Delta) | Đánh giá |
|---|---:|---:|---:|---|
| **Số Requests** | 2.834 | **2.828** | -6 (-0.21%) | Khớp gần như tuyệt đối |
| **Thông lượng (RPS)** | 48.01 | **47.90** | -0.11 (-0.23%) | Khớp trần lý thuyết của 20 users |
| **Độ trễ trung bình** | 5.09 ms | **3.82 ms** | -1.27 ms | Tốt hơn |
| **Độ trễ p50** | 5.0 ms | **4.0 ms** | -1.0 ms | |
| **Độ trễ p95** | 6.0 ms | **5.0 ms** | -1.0 ms | Ổn định |
| **Tỷ lệ lỗi (Failures)** | 0 (0%) | **0 (0%)** | 0 | Đạt chuẩn |
| **Java CPU trung bình** | 19.44% | **13.21%** | -6.23% | Chip AMD EPYC ăn ít CPU hơn |
| **Java RAM tối đa (RSS)**| 543.86 MiB | **553.46 MiB** | +9.60 MiB (+1.77%) | Khớp |

---

### Kịch bản 2: Đặt vé có khóa giao dịch (POST Booking) - 20 Virtual Users, 60 giây

*Fixture: 1.000 chuyến xe mới × 4 ghế = 4.000 vé khả dụng. Mỗi request đặt 1 vé.*

| Chỉ số | Baseline Gốc (Repo) | Lượt Chạy Lại (Rerun) | Chênh lệch (Delta) | Đánh giá |
|---|---:|---:|---:|---|
| **Số Requests** | 2.789 | **2.763** | -26 (-0.93%) | Khớp gần như tuyệt đối |
| **Thông lượng (RPS)** | 47.21 | **46.79** | -0.42 (-0.89%) | Khớp trần lý thuyết của 20 users |
| **Độ trễ trung bình** | 16.09 ms | **14.34 ms** | -1.75 ms | Tốt hơn |
| **Độ trễ p50** | 15.0 ms | **13.0 ms** | -2.0 ms | |
| **Độ trễ p95** | 25.0 ms | **22.0 ms** | -3.0 ms | Ổn định |
| **Tỷ lệ lỗi (Failures)** | 0 (0%) | **0 (0%)** | 0 | Đạt chuẩn |
| **Java CPU trung bình** | 83.02% | **61.23%** | -21.79% | Chip AMD EPYC xử lý tải CPU nhẹ hơn |
| **Java RAM tối đa (RSS)**| 643.30 MiB | **659.88 MiB** | +16.58 MiB (+2.58%) | Khớp |
| **Lệch cân bằng ghế** | **0 chuyến** | **0 chuyến** | **0** | **100% nhất quán dữ liệu** |

---

## 3. Kết luận xác minh

1. **Số liệu trong repo là hoàn toàn chính xác và trung thực:**
   * Thông lượng đo được ở cả hai bài test chỉ chênh lệch **dưới 1%** (GET lệch $-0.23\%$, POST lệch $-0.89\%$).
   * Tỷ lệ lỗi hoàn thành là **0%** trên toàn bộ 60 giây test.
   * Tính toàn vẹn số ghế trong database đạt **100%** (0 chuyến xe bị sai lệch cân bằng ghế).
2. **Tác động của phần cứng:**
   * Phiên chạy này được Kaggle phân bổ CPU **AMD EPYC 7B12** (thay vì Intel Xeon ở bản gốc). Dù dòng chip khác nhau, thông lượng và độ trễ vẫn giữ nguyên vẹn, trong khi hiệu suất tính toán CPU của AMD EPYC tốt hơn (CPU POST giảm từ 83% xuống 61%).

