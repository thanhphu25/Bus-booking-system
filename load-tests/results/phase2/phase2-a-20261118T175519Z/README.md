# Kết quả Kaggle Pha 2A · baseline P1

**Đường tìm chuyến của Pha 1 bị giới hạn bởi CPU của PostgreSQL.** Mọi request `GET /api/trips` có ngày đều quét toàn bộ bảng `trips` (667 buffer mỗi lần), kể cả khi kết quả rỗng. Thông lượng đã bão hòa từ 10 users: lên 20 users, RPS gần như không đổi và độ trễ tăng gấp đôi. Đây là số "trước" cho A1/A2/A3; bản cải tiến sẽ được đo lại cùng P1 trong một phiên Kaggle khác. [Tổng hợp](aggregate.csv) · [Số liệu từng lượt](summary.csv).

## Điều kiện đo

- Kaggle CPU Intel Xeon 2,20 GHz, 4 CPU logic, Java 21, PostgreSQL 16.15, Locust 2.32.10. P1 build từ `fd6b5f3`, working tree sạch. [SHA, hash JAR và cấu hình](manifest.json).
- Fixture tất định có 53.412 chuyến trên 120 tuyến, từ 2026-10-01 đến 2027-03-31, 15.467 mốc giờ khởi hành có từ hai chuyến trở lên. Mỗi lượt dùng database khôi phục từ cùng snapshot đã chạy Flyway V1–V16 và `VACUUM ANALYZE`. [SQL sinh dữ liệu](fixture.sql) · [Thống kê fixture](fixture_stats.json).
- Bốn bộ lọc cho ngày 2026-12-15: tuyến không có chuyến (0 dòng), tuyến ít chuyến (3), tuyến đông (40) và chỉ lọc ngày (286). Locust chạy closed loop, không chờ giữa các request, mỗi mức 10 và 20 users đo 120 giây sau 60 giây warm-up. Ba lượt lặp, tổng 24 lượt đo, 735.400 request và 0 lỗi. [Locustfile](locustfile.py).
- Trước khi đo tải, notebook đối chiếu từng response với số đếm SQL, thứ tự `departureTime`, ngày và tuyến. [ID trả về](trace/P1/response_ids.json).

## Độ trễ và thông lượng

Mỗi ô ghi trung vị của ba lượt, kèm min–max trong ngoặc.

| Bộ lọc | Dòng | p95 · 10 users (ms) | RPS · 10 users | p95 · 20 users (ms) | RPS · 20 users | Byte/response |
|---|---:|---:|---:|---:|---:|---:|
| Không có chuyến | 0 | 44,02 (43,85–44,02) | 302,8 (302,3–303,7) | 100,76 (100,40–100,94) | 304,1 (304,1–305,6) | 2 |
| Ít chuyến | 3 | 44,51 (44,38–45,07) | 297,2 (295,0–298,1) | 104,02 (103,83–104,65) | 297,0 (296,0–297,4) | 1.344 |
| Tuyến đông | 40 | 52,79 (52,78–52,87) | 243,2 (243,0–243,3) | 127,00 (126,09–127,17) | 242,2 (241,7–242,7) | 17.959 |
| Chỉ lọc ngày | 286 | 75,24 (74,73–75,32) | 178,1 (178,0–178,5) | 161,12 (160,68–161,75) | 178,3 (177,6–178,5) | 128.406 |

RPS ở 10 và 20 users gần như bằng nhau, còn p50 tăng từ 32,73 lên 64,40 ms với bộ lọc rỗng. Theo Little's law, 10 / 302,8 ≈ 33 ms và 20 / 304,1 ≈ 66 ms, nên phần độ trễ tăng thêm ở 20 users là thời gian xếp hàng.

## Chi phí SQL và CPU

Số liệu lấy từ `pg_stat_statements` trong cửa sổ đo, chia cho số request, ở mức 10 users.

| Bộ lọc | Lệnh SQL/request | Thời gian SQL/request (ms) | Buffer/request | CPU PostgreSQL (core) | CPU Java (core) |
|---|---:|---:|---:|---:|---:|
| Không có chuyến | 1 | 25,09 | 667 | 3,38 | 0,27 |
| Ít chuyến | 1 | 25,48 | 667 | 3,39 | 0,26 |
| Tuyến đông | 1 | 32,12 | 667 | 3,29 | 0,38 |
| Chỉ lọc ngày | 1 | 34,11 | 686 | 2,55 | 1,07 |

PostgreSQL dùng khoảng 3,3–3,4 trong 4 core với ba bộ lọc có tuyến. Với bộ lọc chỉ có ngày, Java dùng khoảng 1,07 core vì mỗi response chứa 286 chuyến kèm tuyến, địa điểm, xe và nhà xe, khoảng 449 byte mỗi chuyến. [SQL của một lượt](runs/01_P1/zero_u10_sql.csv).

## Query plan

Plan được ghi bằng `auto_explain` trên một database riêng, 15 vòng cho mỗi bộ lọc, không trong lúc đo tải. [Tóm tắt](trace_summary.csv) · [Từng plan](trace/P1/plans.csv) · [Plan JSON đầy đủ](trace/P1/plans.jsonl).

| Bộ lọc | Generic plan / số lần | Thời gian SQL trung vị (ms) | Dòng trả |
|---|---:|---:|---:|
| Không có chuyến | 14 / 15 | 6,14 | 0 |
| Ít chuyến | 14 / 15 | 6,17 | 3 |
| Tuyến đông | 14 / 15 | 6,80 | 40 |
| Chỉ lọc ngày | 15 / 15 | 8,37 | 286 |
| Không lọc | 1 / 1 | 458,37 | 53.412 |

- `searchFiltered` là một query JPQL catch-all cho mọi tổ hợp bộ lọc. SQL Hibernate sinh ra có dạng `($1=true or origin=$2) and … and ($5=true or departure_time trong ngày)`. Trong generic plan, điều kiện trên `trips` trở thành `$5 OR (departure_time >= $6 AND departure_time < $7)`.
- Trace có nhiều generic plan vì notebook đã gọi `no_filter` trước các vòng trace. PostgreSQL chỉ dùng generic plan khi cost của nó (2.192) thấp hơn trung bình cost các custom plan trước đó trên cùng connection, và plan `no_filter` có cost khoảng 14.554 nên kéo trung bình lên. Lượt đo tải không gọi `no_filter`. Chạy lại cùng JAR và fixture trên PostgreSQL 16.15 local theo thứ tự của lượt đo tải cho 62/62 custom plan. Với P1, cả hai loại plan đều quét toàn bảng 667 buffer, nên số đo ở trên không đổi. Notebook đã chuyển `no_filter` xuống cuối cho các lần chạy sau.
- Mọi bộ lọc đều dùng `Seq Scan` trên `trips`, loại 53.126 dòng để giữ 286 chuyến của ngày. Điều kiện tuyến chỉ được áp dụng sau đó, khi join với `routes`. Vì vậy bộ lọc trả 0 dòng vẫn tốn 667 buffer như bộ lọc trả 40 dòng.
- Bảng `trips` chỉ còn khóa chính. V16 đã bỏ `idx_trips_route_id` và chưa có index nào trên `departure_time`.
- Không lọc trả toàn bộ 53.412 chuyến, và bước sort dùng `external merge` trên đĩa vì vượt `work_mem` 4 MB.

## Hướng cải tiến cần kiểm chứng

Đây là giả thuyết rút từ plan, chưa phải kết quả đo.

- **A1:** index `trips (departure_time, route_id)` trong V18. Generic plan không dùng được index này vì điều kiện `$5 OR …`, nên tác dụng của nó phụ thuộc vào việc PostgreSQL giữ custom plan. Đã đo cùng phiên với P1: [phase2-a-20261124T120538Z](../phase2-a-20261124T120538Z/README.md).
- **A2:** phân trang tại DB với thứ tự `departure_time, id` để giới hạn số dòng và byte của bộ lọc chỉ có ngày và không lọc. Đã đo cùng P1: [phase2-a-20261124T190521Z](../phase2-a-20261124T190521Z/README.md).
- **A3:** projection thay cho entity graph để giảm cột đọc và công việc serialize ở Java. Đã đo cùng P1: [phase2-a-20261124T190521Z](../phase2-a-20261124T190521Z/README.md).

## Giới hạn

- Locust, Java và PostgreSQL dùng chung CPU của Kaggle.
- CPU có thể khác giữa các phiên Kaggle, nên chỉ so sánh các bản đo trong cùng một lần chạy.
- Thời gian SQL trong bảng query plan được đo khi chạy một mình. Thời gian SQL dưới tải cao hơn vì nhiều query tranh CPU.
