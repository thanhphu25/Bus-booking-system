# Kết quả Kaggle Pha 2A · P1 và A1

**Index V18 của A1 làm cả bốn bộ lọc nhanh hơn rõ rệt, đo cùng phiên với P1.** Ở 10 users, p95 giảm 41–77% và RPS tăng 81–352%. Ở 20 users, p95 giảm 44–81%. Khoảng min–max của P1 và A1 không chồng nhau ở bộ lọc hay mức users nào. Query plan cho thấy nguyên nhân: mỗi request của A1 đọc 6–213 buffer thay vì 667–686, và mọi plan trong trace của cả hai bản đều là custom plan. [Tổng hợp](aggregate.csv) · [Số liệu từng lượt](summary.csv).

## Điều kiện đo

- Kaggle CPU Intel Xeon 2,20 GHz, 4 CPU logic, RAM 31,3 GiB, Java 21.0.12, PostgreSQL 16.15, Locust 2.32.10. P1 build từ `fd6b5f3`, A1 từ `6d0e024` (thêm `V18__add_trip_search_index.sql`), cả hai working tree sạch. [SHA, hash JAR và cấu hình](manifest.json).
- Cùng fixture và cùng bốn bộ lọc với [lần đo P1 trước](../phase2-a-20261118T175519Z/README.md): SQL sinh dữ liệu có cùng SHA-256, 53.412 chuyến, ngày lọc 2026-12-15. Mỗi lượt tạo database từ snapshot V1–V16 đã `VACUUM ANALYZE`, cho JAR của bản đó chạy Flyway (A1 thêm V18), rồi `ANALYZE`. [SQL sinh dữ liệu](fixture.sql) · [Thống kê fixture](fixture_stats.json).
- Locust chạy closed loop, không chờ giữa các request, mỗi mức 10 và 20 users đo 120 giây sau 60 giây warm-up. Ba lượt, đảo thứ tự P1/A1 giữa các lượt: 48 lượt đo, 3.900.076 request, 0 lỗi. Notebook chạy hết 108,6 phút. [Locustfile](locustfile.py).
- Trước khi đo tải, notebook đối chiếu từng response với số đếm SQL, ngày, tuyến và thứ tự `departureTime`; A1 trả đúng tập chuyến như P1 ở cả năm bộ lọc. [ID của P1](trace/P1/response_ids.json) · [ID của A1](trace/A1/response_ids.json).

## Độ trễ và thông lượng

Mỗi ô ghi trung vị của ba lượt, kèm min–max trong ngoặc.

| Bộ lọc | Dòng | Bản | p95 · 10 users (ms) | RPS · 10 users | p95 · 20 users (ms) | RPS · 20 users |
|---|---:|---|---:|---:|---:|---:|
| Không có chuyến | 0 | P1 | 40,12 (39,63–40,50) | 336,0 (334,5–337,9) | 90,80 (90,38–92,63) | 340,1 (333,7–341,5) |
| | | A1 | 9,23 (9,11–9,27) | 1.518,9 (1.516,4–1.539,2) | 17,30 (17,22–18,38) | 1.531,3 (1.444,4–1.537,7) |
| Ít chuyến | 3 | P1 | 41,01 (40,14–41,22) | 326,3 (325,8–331,8) | 94,48 (94,26–95,11) | 329,2 (328,3–329,6) |
| | | A1 | 9,94 (9,79–10,45) | 1.428,2 (1.360,5–1.444,4) | 18,88 (18,72–19,11) | 1.425,1 (1.403,9–1.441,9) |
| Tuyến đông | 40 | P1 | 48,31 (48,13–48,73) | 268,3 (266,2–269,6) | 114,94 (114,78–121,98) | 267,9 (254,5–268,4) |
| | | A1 | 14,15 (14,15–14,34) | 1.025,1 (1.010,8–1.026,6) | 27,41 (27,40–27,88) | 1.031,0 (1.013,3–1.032,7) |
| Chỉ lọc ngày | 286 | P1 | 71,58 (69,90–71,63) | 189,5 (188,9–192,9) | 149,94 (149,83–159,92) | 190,9 (181,8–191,0) |
| | | A1 | 42,27 (42,04–42,85) | 342,4 (336,5–342,7) | 84,34 (83,36–85,92) | 340,8 (336,2–346,0) |

Thay đổi của A1 so với P1, tính trên trung vị:

| Bộ lọc | p95 · 10 users | RPS · 10 users | p95 · 20 users | RPS · 20 users |
|---|---:|---:|---:|---:|
| Không có chuyến | −77,0% | +352,0% | −81,0% | +350,3% |
| Ít chuyến | −75,8% | +337,7% | −80,0% | +332,9% |
| Tuyến đông | −70,7% | +282,0% | −76,2% | +284,9% |
| Chỉ lọc ngày | −41,0% | +80,7% | −43,8% | +78,6% |

Ở cả hai bản, RPS ở 10 và 20 users gần như bằng nhau: hệ thống đã bão hòa từ 10 users, nên phần độ trễ tăng thêm ở 20 users là thời gian xếp hàng.

## Chi phí SQL và CPU

Số liệu lấy từ `pg_stat_statements` và mẫu CPU trong cửa sổ đo, ở mức 10 users. CPU tính bằng số core trung bình. [SQL của một lượt A1](runs/01_A1/zero_u10_sql.csv).

| Bộ lọc | Bản | Thời gian SQL/request (ms) | Buffer/request | CPU PostgreSQL | CPU Java | CPU Locust |
|---|---|---:|---:|---:|---:|---:|
| Không có chuyến | P1 | 21,31 | 667 | 3,30 | 0,32 | 0,26 |
| | A1 | 0,10 | 6 | 1,71 | 0,85 | 0,81 |
| Ít chuyến | P1 | 21,58 | 667 | 3,28 | 0,32 | 0,27 |
| | A1 | 0,18 | 19 | 1,70 | 0,94 | 0,78 |
| Tuyến đông | P1 | 27,80 | 667 | 3,21 | 0,44 | 0,24 |
| | A1 | 0,86 | 167 | 1,65 | 1,31 | 0,65 |
| Chỉ lọc ngày | P1 | 29,91 | 686 | 2,46 | 1,14 | 0,27 |
| | A1 | 7,46 | 213 | 1,46 | 1,94 | 0,41 |

- Với P1, mỗi request quét cả bảng `trips`, nên PostgreSQL dùng 3,2–3,3 trong 4 core ở ba bộ lọc có tuyến. A1 chỉ đọc phần index của ngày cần tìm: thời gian SQL mỗi request giảm từ 21–30 ms xuống 0,1–7,5 ms, và PostgreSQL chỉ còn dùng 1,5–1,7 core dù phục vụ gấp 1,8–4,5 lần số request.
- Buffer mỗi request lúc đo tải bằng đúng số trong trace, nên dưới tải PostgreSQL vẫn dùng custom plan có index.
- Điểm nghẽn đã chuyển khỏi database. Với bộ lọc chỉ có ngày, Java dùng 1,94 core để dựng và serialize 286 chuyến (128 KB) mỗi response. Với ba bộ lọc rẻ, Locust dùng 0,65–0,81 core, gần mức một tiến trình Python chạy được, nên RPS của A1 ở các bộ lọc này có thể đang bị máy tạo tải giới hạn một phần.

## Query plan

Plan ghi bằng `auto_explain` trên database riêng của từng bản, 15 vòng cho mỗi bộ lọc đo tải, `no_filter` chạy một lần sau cùng, không trong lúc đo tải. [Tóm tắt](trace_summary.csv) · [Plan P1](trace/P1/plans.csv) · [Plan A1](trace/A1/plans.csv).

| Bộ lọc | P1: cách đọc `trips`, buffer | A1: cách đọc `trips`, buffer | Thời gian SQL trung vị P1 → A1 (ms) |
|---|---|---|---:|
| Không có chuyến | Seq Scan, 667 | Index Scan V18, 6 | 4,89 → 0,10 |
| Ít chuyến | Seq Scan, 667 | Index Scan V18, 19 | 4,99 → 0,12 |
| Tuyến đông | Seq Scan, 667 | Index Scan V18, 167 | 6,79 → 0,48 |
| Chỉ lọc ngày | Seq Scan, 744 | Index Scan V18, 213 | 7,37 → 2,56 |
| Không lọc (một lần) | Seq Scan rồi sort trên đĩa, 667 | Index Scan hết index, 41.826 | 423,5 → 491,3 |

- Cả 61 plan của mỗi bản đều là custom plan. Lần đo P1 trước có generic plan vì notebook gọi `no_filter` trước các vòng trace; notebook đã chuyển `no_filter` xuống cuối.
- Với bộ lọc có tuyến, `route_id` được so ngay trong index `idx_trips_departure_time_route_id`, nên heap chỉ đọc đúng các chuyến khớp.
- **Không lọc chậm hơn ở A1**, theo một lần đo duy nhất mỗi bản. Planner của A1 đi hết index theo thứ tự `departure_time` để khỏi phải sort, đọc 41.624 buffer trong shared buffers và 202 buffer từ đĩa. P1 quét bảng 667 buffer rồi sort trên đĩa vì vượt `work_mem` 4 MB. Bộ lọc này không đưa vào đo tải.

## So với lần đo P1 trước

Lần đo P1 ngày 2026-11-18 chạy ở phiên Kaggle khác, cùng tên CPU, cùng source và cùng fixture. Ở bộ lọc không có chuyến, 10 users, lần đó có p95 44,02 ms và 302,8 RPS; lần này là 40,12 ms và 336,0 RPS. Cùng code, cùng dữ liệu mà lệch khoảng 10% giữa hai phiên, nên chỉ so P1 với A1 trong cùng phiên này. JAR được build lại trong mỗi phiên nên hash JAR khác nhau dù source SHA giống nhau.

## Giới hạn

- Locust, Java và PostgreSQL dùng chung 4 CPU của Kaggle; ở các bộ lọc rẻ của A1, máy tạo tải dùng gần một core.
- Số liệu từng request (`runs/*/*_requests.csv`, 85 MB, là nguồn tính p50/p95/p99) không đưa vào git vì quá nặng. Toàn bộ output tải từ Kaggle, gồm cả các file này, nằm trong [file ZIP](../phase2-a-20261124T120538Z.zip).
- Thời gian SQL trong bảng query plan được đo khi chạy một mình. Dưới tải, thời gian SQL cao hơn vì nhiều query tranh CPU.
- Không lọc chỉ có một mẫu cho mỗi bản.
