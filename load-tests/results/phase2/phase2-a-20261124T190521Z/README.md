# Kết quả Kaggle Pha 2A · P1, A2 và A3

**Khi người dùng xem trang đầu, A3 giảm p95 73–74% và phục vụ gấp 3,9–4,2 lần số request so với P1 trả toàn bộ kết quả.** Kết quả trả về vẫn khớp từng trường với P1. Phép đo này tách được hai tác dụng, mỗi cái đo trong cùng một bản hoặc giữa hai bản cạnh nhau:

- **Trang đầu (A2):** với bộ lọc chỉ có ngày (286 chuyến), trang 20 chuyến giảm p95 52% và tăng gấp đôi RPS so với trả đủ. Với tuyến đông (40 chuyến), mức giảm chỉ khoảng 7%. Database đọc gần như cùng số trang dữ liệu; phần tiết kiệm nằm ở số dòng chuyển sang Java, serialize và byte gửi đi.
- **Projection (A3):** SQL giữ nguyên, chỉ lấy 14 cột thay vì 36 và không dựng entity. p95 giảm 10–33% ở các bộ lọc có trả chuyến, càng nhiều dòng thì càng giảm nhiều. Với bộ lọc không có kết quả, chênh lệch nằm trong dao động.

Không có generic plan nào trong trace, và không có request lỗi. [Tổng hợp](aggregate.csv) · [Số liệu từng lượt](summary.csv).

## Điều kiện đo

- Kaggle CPU Intel Xeon 2,20 GHz, 4 CPU logic, RAM 31,3 GiB, Java 21.0.12, PostgreSQL 16.15, Locust 2.32.10. Ba bản, working tree đều sạch: P1 `fd6b5f3`, A2 `5966fc5` (thêm `page`/`size`, sắp theo `departure_time, id`), A3 `e78bd45` (`TripSearchQuery` và projection). Không đo lại A1, vì A1 đã được đo cùng P1 trong [lần chạy trước](../phase2-a-20261124T120538Z/README.md). [SHA, hash JAR và cấu hình](manifest.json).
- Fixture và bốn bộ lọc giống các lần trước: 53.412 chuyến, ngày lọc 2026-12-15. A2 và A3 đo thêm trang đầu `page=0&size=20` của tuyến đông và của bộ lọc chỉ có ngày. [SQL sinh dữ liệu](fixture.sql) · [Thống kê fixture](fixture_stats.json).
- 10 và 20 users, không chờ giữa các request, warm-up 60 giây rồi đo 120 giây. Ba lượt, đảo thứ tự các bản giữa các lượt: 96 lượt đo, 8.816.778 request, 0 lỗi. Notebook chạy hết 212,3 phút.
- Trước khi đo tải, notebook kiểm tra từng response:
  - Số chuyến, ngày và tuyến.
  - A2 và A3 phải sắp tăng chặt theo `departureTime` rồi `id`, và mỗi trang đầu phải đúng 20 ID tính bằng SQL.
  - JSON của từng chuyến được so với P1 qua SHA-256. Riêng trang đầu được so với 20 chuyến đầu của kết quả đầy đủ của P1 sau khi sắp lại theo cùng thứ tự.

  Cả 8 bộ lọc của A2 và A3 đều khớp. [Digest của A2](trace/A2/response_digests.json) · [Digest của A3](trace/A3/response_digests.json).

## Độ trễ và thông lượng

Mỗi ô ghi trung vị của ba lượt, kèm min–max trong ngoặc.

| Bộ lọc | Dòng | Bản | p95 · 10 users (ms) | RPS · 10 users | p95 · 20 users (ms) | RPS · 20 users |
|---|---:|---|---:|---:|---:|---:|
| Không có chuyến | 0 | P1 | 45,27 (44,21–46,40) | 306,7 (303,8–312,3) | 97,26 (97,09–100,28) | 318,4 (308,8–320,1) |
| | | A2 | 11,13 (10,79–11,25) | 1.291,8 (1.284,9–1.324,0) | 20,42 (20,00–20,50) | 1.317,1 (1.301,2–1.345,6) |
| | | A3 | 10,41 (10,37–10,86) | 1.361,4 (1.299,2–1.364,4) | 19,30 (19,13–20,42) | 1.375,3 (1.295,7–1.387,0) |
| Ít chuyến | 3 | P1 | 44,44 (43,94–45,09) | 306,4 (304,5–307,9) | 100,74 (100,02–100,83) | 308,3 (308,0–309,2) |
| | | A2 | 11,92 (11,70–11,92) | 1.207,0 (1.203,7–1.222,5) | 22,06 (22,02–23,48) | 1.241,6 (1.161,9–1.249,2) |
| | | A3 | 10,69 (10,58–11,70) | 1.324,9 (1.227,2–1.339,9) | 20,97 (20,41–21,78) | 1.279,1 (1.242,9–1.303,6) |
| Tuyến đông | 40 | P1 | 51,70 (51,39–52,52) | 253,2 (251,9–255,1) | 125,29 (120,95–129,11) | 246,5 (239,3–253,5) |
| | | A2 | 16,38 (15,91–17,45) | 881,7 (828,4–909,8) | 31,53 (30,77–33,67) | 899,1 (838,3–922,2) |
| | | A3 | 13,72 (13,34–13,82) | 1.046,5 (1.036,9–1.078,1) | 26,39 (26,29–27,31) | 1.046,2 (1.029,3–1.047,8) |
| Tuyến đông · trang đầu | 20 | A2 | 15,20 (14,97–15,74) | 950,0 (918,2–967,1) | 29,92 (28,54–30,55) | 946,8 (921,1–985,7) |
| | | A3 | 13,57 (13,37–13,86) | 1.057,2 (1.038,4–1.077,6) | 25,57 (25,43–26,60) | 1.070,7 (1.044,1–1.088,1) |
| Chỉ lọc ngày | 286 | P1 | 76,56 (76,15–77,13) | 178,2 (177,7–179,1) | 157,73 (156,34–159,29) | 177,5 (177,2–179,9) |
| | | A2 | 47,61 (45,84–50,78) | 305,6 (285,4–316,8) | 93,29 (91,18–99,19) | 309,1 (290,9–316,5) |
| | | A3 | 32,11 (32,08–32,89) | 449,4 (434,8–452,7) | 62,71 (62,65–63,26) | 448,8 (447,5–450,4) |
| Chỉ lọc ngày · trang đầu | 20 | A2 | 22,99 (22,20–23,77) | 629,2 (608,5–648,2) | 45,04 (43,25–45,66) | 639,9 (626,1–662,6) |
| | | A3 | 20,64 (20,39–20,85) | 702,0 (698,9–718,3) | 39,39 (39,12–39,74) | 723,0 (716,5–728,6) |

Ở mọi bản, RPS ở 10 và 20 users gần như bằng nhau, nên hệ thống đã bão hòa từ 10 users. Các phần dưới dùng số ở 10 users và tính phần trăm trên trung vị.

### Trang đầu tiết kiệm gì

So trong cùng một bản: trả đủ kết quả với trang đầu `page=0&size=20`.

| Bản · bộ lọc | Dòng | Byte/response | Buffer/request | p95 | RPS | CPU Java (core) |
|---|---:|---:|---:|---:|---:|---:|
| A2 · tuyến đông | 40 → 20 | 17.959 → 8.981 | 167 → 167 | −7,2% | +7,7% | 1,38 → 1,17 |
| A2 · chỉ lọc ngày | 286 → 20 | 128.406 → 8.966 | 213 → 163 | −51,7% | +105,9% | 1,97 → 0,94 |
| A3 · tuyến đông | 40 → 20 | 17.959 → 8.981 | 167 → 167 | −1,1% (khoảng min–max chồng nhau) | +1,0% | 1,15 → 0,99 |
| A3 · chỉ lọc ngày | 286 → 20 | 128.406 → 8.966 | 213 → 163 | −35,7% | +56,2% | 1,63 → 0,76 |

- Database gần như không đọc ít đi. Với tuyến đông, plan vẫn lấy đủ 40 chuyến, sort xong mới cắt, nên buffer giữ nguyên 167. Với bộ lọc chỉ có ngày, buffer chỉ giảm từ 213 xuống 163, vì với 20 dòng planner chuyển sang nested loop và mỗi dòng phải tra 5 bảng nhỏ qua index.
- Phần lợi nằm ở số dòng, byte và CPU Java. Cắt càng nhiều dòng thì lợi càng rõ. Sau khi đã có projection (A3), trang đầu của tuyến đông không còn khác biệt rõ.

### Projection giúp gì

So A2 với A3. Hai bản có cùng index, cùng câu `WHERE`/`ORDER BY`/`fetch first`; A3 chỉ chọn 14 cột thay vì 36 và đọc thẳng vào record thay vì dựng entity.

| Bộ lọc | p95 | RPS | CPU Java (core) | Thời gian SQL/request (ms) | RSS Java (MiB) |
|---|---:|---:|---:|---:|---:|
| Không có chuyến | −6,4% (chồng nhau) | +5,4% | 0,96 → 0,94 | 0,113 → 0,112 | 605 → 584 |
| Ít chuyến | −10,3% | +9,8% | 1,06 → 0,96 | 0,197 → 0,168 | 606 → 586 |
| Tuyến đông | −16,2% | +18,7% | 1,38 → 1,15 | 0,857 → 0,506 | 606 → 586 |
| Chỉ lọc ngày | −32,5% | +47,0% | 1,97 → 1,63 | 7,738 → 4,931 | 607 → 587 |
| Tuyến đông · trang đầu | −10,7% | +11,3% | 1,17 → 0,99 | 0,700 → 0,437 | 607 → 587 |
| Chỉ lọc ngày · trang đầu | −10,2% | +11,6% | 0,94 → 0,76 | 1,300 → 0,968 | 607 → 604 |

- Buffer mỗi request của hai bản bằng nhau ở mọi bộ lọc, nên database đọc cùng các trang. Dù vậy, thời gian SQL mỗi request vẫn giảm, ví dụ từ 7,7 xuống 4,9 ms với bộ lọc chỉ có ngày. Đây là giả thuyết, chưa kiểm chứng riêng: có thể vì PostgreSQL chỉ phải lấy và gửi 14 cột thay vì 36.
- Lợi ích tăng theo số dòng trả về. Với bộ lọc không có kết quả, A2 và A3 làm gần như cùng một việc.

### Tác động tổng

Với các bộ lọc trên 20 chuyến, phép so là P1 trả toàn bộ kết quả với A3 trả trang đầu, tức trường hợp người dùng xem trang đầu. Với bộ lọc có tối đa 20 chuyến, trang đầu chính là toàn bộ kết quả.

| Bộ lọc | So sánh | p95 · 10 users (ms) | RPS · 10 users | p95 · 20 users (ms) | RPS · 20 users |
|---|---|---:|---:|---:|---:|
| Không có chuyến | P1 → A3 | 45,27 → 10,41 (−77,0%) | 306,7 → 1.361,4 (gấp 4,4) | 97,26 → 19,30 (−80,2%) | 318,4 → 1.375,3 (gấp 4,3) |
| Ít chuyến | P1 → A3 | 44,44 → 10,69 (−75,9%) | 306,4 → 1.324,9 (gấp 4,3) | 100,74 → 20,97 (−79,2%) | 308,3 → 1.279,1 (gấp 4,1) |
| Tuyến đông | P1 trả đủ → A3 trang đầu | 51,70 → 13,57 (−73,7%) | 253,2 → 1.057,2 (gấp 4,2) | 125,29 → 25,57 (−79,6%) | 246,5 → 1.070,7 (gấp 4,3) |
| Chỉ lọc ngày | P1 trả đủ → A3 trang đầu | 76,56 → 20,64 (−73,0%) | 178,2 → 702,0 (gấp 3,9) | 157,73 → 39,39 (−75,0%) | 177,5 → 723,0 (gấp 4,1) |

## Chi phí SQL và CPU

Số liệu lấy từ `pg_stat_statements` và mẫu CPU trong cửa sổ đo, ở mức 10 users. CPU tính bằng số core trung bình.

| Bộ lọc | Bản | Thời gian SQL/request (ms) | Buffer/request | Dòng/request | CPU PostgreSQL | CPU Java | CPU Locust |
|---|---|---:|---:|---:|---:|---:|---:|
| Không có chuyến | P1 | 22,070 | 667 | 0 | 3,12 | 0,45 | 0,28 |
| | A2 | 0,113 | 6 | 0 | 1,64 | 0,96 | 0,77 |
| | A3 | 0,112 | 6 | 0 | 1,59 | 0,94 | 0,79 |
| Ít chuyến | P1 | 22,182 | 667 | 3 | 3,18 | 0,39 | 0,28 |
| | A2 | 0,197 | 19 | 3 | 1,61 | 1,06 | 0,74 |
| | A3 | 0,168 | 19 | 3 | 1,62 | 0,96 | 0,78 |
| Tuyến đông | P1 | 28,252 | 667 | 40 | 3,11 | 0,50 | 0,26 |
| | A2 | 0,857 | 167 | 40 | 1,56 | 1,38 | 0,63 |
| | A3 | 0,506 | 167 | 40 | 1,59 | 1,15 | 0,73 |
| Tuyến đông · trang đầu | A2 | 0,700 | 167 | 20 | 1,74 | 1,17 | 0,64 |
| | A3 | 0,437 | 167 | 20 | 1,76 | 0,99 | 0,72 |
| Chỉ lọc ngày | P1 | 30,455 | 686 | 286 | 2,37 | 1,19 | 0,29 |
| | A2 | 7,738 | 213 | 286 | 1,38 | 1,97 | 0,42 |
| | A3 | 4,931 | 213 | 286 | 1,48 | 1,63 | 0,57 |
| Chỉ lọc ngày · trang đầu | A2 | 1,300 | 163 | 20 | 2,25 | 0,94 | 0,50 |
| | A3 | 0,968 | 163 | 20 | 2,36 | 0,76 | 0,54 |

- Trang đầu của bộ lọc chỉ có ngày giờ tốn CPU ở PostgreSQL nhiều hơn ở Java: 2,36 so với 0,76 core ở A3. Phần còn lại chủ yếu là nested loop tra các bảng nhỏ cho từng dòng. Nếu cần tối ưu tiếp thì đây là chỗ đáng xem, nhưng phép đo này không làm.
- Với các bộ lọc rẻ, Locust dùng đến 0,79 core, gần mức tối đa của một tiến trình. Vì vậy RPS của A2 và A3 ở các bộ lọc này có thể đang bị máy tạo tải giới hạn một phần.

## Query plan

Plan được ghi bằng `auto_explain` trên database riêng của từng bản: 15 vòng cho mỗi bộ lọc đo tải, còn `no_filter` và `no_filter_page0` mỗi cái chạy một lần sau cùng. Không có generic plan nào trên 61 plan của P1, 92 plan của A2 và 92 plan của A3. [Tóm tắt](trace_summary.csv) · [Plan P1](trace/P1/plans.csv) · [Plan A2](trace/A2/plans.csv) · [Plan A3](trace/A3/plans.csv).

| Bộ lọc | P1: buffer · SQL trung vị | A2: buffer · SQL trung vị | A3: buffer · SQL trung vị |
|---|---:|---:|---:|
| Không có chuyến | 667 · 8,69 ms | 6 · 0,11 ms | 6 · 0,12 ms |
| Ít chuyến | 667 · 5,92 ms | 19 · 0,16 ms | 19 · 0,12 ms |
| Tuyến đông | 667 · 7,84 ms | 167 · 0,61 ms | 167 · 0,39 ms |
| Tuyến đông · trang đầu | — | 167 · 0,58 ms | 167 · 0,29 ms |
| Chỉ lọc ngày | 686 · 8,15 ms | 213 · 3,29 ms | 213 · 1,40 ms |
| Chỉ lọc ngày · trang đầu | — | 163 · 0,66 ms | 163 · 0,38 ms |
| Không lọc (một lần) | 667 · 351,6 ms | 41.624 · 508,8 ms | 667 · 344,0 ms |
| Không lọc · trang đầu (một lần) | — | 168 · 0,39 ms | 168 · 0,30 ms |

- Câu SQL của A2 giống P1 nhưng thêm `id` vào `ORDER BY`; trang đầu thêm `fetch first $8 rows only`. A3 giữ nguyên các phần đó và chỉ chọn 14 cột thay vì 36.
- Mọi bộ lọc có ngày của A2 và A3 đều dùng index `idx_trips_departure_time_route_id` của A1.
- Với bộ lọc không lọc và không phân trang: A2 đi hết index theo thứ tự để khỏi phải sort, nên chậm hơn P1. A3 quay lại quét bảng rồi sort như P1, vì dòng hẹp hơn làm sort rẻ hơn. Bộ lọc này không đưa vào đo tải. Khi có phân trang, nó chỉ còn khoảng 0,3–0,4 ms.

## So với các phiên trước

Cùng code, cùng dữ liệu, cùng tên CPU, nhưng P1 với bộ lọc không có chuyến ở 10 users ra khác nhau giữa các phiên Kaggle:

| Phiên | p95 | RPS |
|---|---:|---:|
| 18/11 | 44,02 ms | 302,8 |
| Sáng 24/11 | 40,12 ms | 336,0 |
| Lần này | 45,27 ms | 306,7 |

Dao động khoảng 10% như vậy là lý do chỉ so các bản trong cùng một phiên.

## Giới hạn

- Locust, Java và PostgreSQL dùng chung 4 CPU của Kaggle. Ở các bộ lọc rẻ, máy tạo tải dùng gần một core.
- Số liệu từng request (`runs/*/*_requests.csv`, 210 MB, là nguồn tính p50/p95/p99) không đưa vào git vì quá nặng. Toàn bộ output tải từ Kaggle, gồm cả các file này, nằm trong [file ZIP](../phase2-a-20261124T190521Z.zip).
- Notebook chỉ đo trang đầu. Trang sâu, với `OFFSET` lớn, chưa được đo.
- Thời gian SQL trong bảng query plan được đo khi chạy một mình.
- Bộ lọc không lọc chỉ có một mẫu cho mỗi bản.
