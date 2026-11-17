# BusBooking | Kế hoạch thực hiện Pha 2

**Đề tài:** Cải tiến đường đọc tìm chuyến và đường ghi đặt vé trong kiến trúc modular monolith của BusBooking.

**Bản gốc:** Pha 1 tại commit `fd6b5f3026412d2359d70bfad681fc0773c8bcae`. Giữ một ứng dụng Spring Boot và một PostgreSQL. Ba phần chính là **A: mô hình đọc riêng cho tìm chuyến**, **B: idempotency bền vững cho đặt vé**, **C: đường truy cập dữ liệu chuyên biệt cho tạo booking, giảm công việc trong vùng khóa**. Đây là kế hoạch triển khai và đo; các kết quả Pha 2 phải được điền sau khi chạy thực tế.

## 1. Căn cứ chọn cải tiến và cách đáp ứng đề bài

Theo [đề bài](2026.md), Pha 2 cần xuất phát từ hệ thống Pha 1 hoặc đặc tả nghiệp vụ, thay đổi thiết kế để cải thiện thuộc tính chất lượng, giải thích lý do và đánh giá trước/sau trên một cấu hình phần cứng. Không cần chuyển sang microservices để chứng minh cải tiến kiến trúc.

| Phần | Hạn chế có căn cứ trong Pha 1 | Thay đổi thiết kế | Thuộc tính chất lượng và bằng chứng chính |
|---|---|---|---|
| **A — Tìm chuyến** | [README](../README.md) và [thiết kế DB](02-database-design.md#25-index-và-tra-cứu) nêu truy vấn chưa phân trang, một số index hoãn ở V16. `TripRepository` dùng chung cho tìm kiếm và thao tác ghi; tìm kiếm tải entity cùng các quan hệ rồi ánh xạ qua domain sang response. | Tách query port và mô hình kết quả tìm chuyến khỏi repository phục vụ ghi; adapter đọc bằng projection, phân trang tại DB; chọn index theo query plan. | Hiệu năng và hiệu quả sử dụng tài nguyên: số dòng/cột đọc, byte response, thời gian SQL, p95, CPU và RPS. |
| **B — Gửi lại yêu cầu đặt vé** | README đề xuất idempotency. `BookingService.create` bảo vệ số ghế bằng transaction/khóa nhưng mỗi POST hợp lệ vẫn có thể tạo booking mới cho cùng một lần mua. | Nhận diện ý định mua theo người dùng, lưu key và kết quả trong cùng transaction tạo booking/trừ ghế; DB phân xử request trùng. | Độ tin cậy khi client retry: không tạo booking/trừ ghế thừa; đo thêm chi phí lần tạo đầu và độ trễ replay. |
| **C — Tạo booking** | README đề xuất đo và giảm thời gian giữ khóa. `findByIdForUpdate` khóa dòng Trip, sau đó `TripPersistenceMapper.toDomain` đọc thêm Route, hai Location, Vehicle và Operator; trong khi `BookingService.create` chỉ cần ID, trạng thái, giá và ghế trống. | Tạo port và snapshot riêng cho việc tạo booking; đọc scalar từ dòng Trip đã khóa, không dựng mô hình chi tiết để hiển thị trong đường ghi. | Hiệu quả sử dụng DB và xử lý đồng thời: giảm SELECT không cần thiết trong transaction, đo p95/RPS/CPU với tải phân tán và tải tập trung cùng chuyến. |

**Phân biệt bằng chứng với giả thuyết.** Việc trả toàn bộ kết quả, thiếu nhận diện request trùng và mapper đọc quan hệ là quan sát từ code. Số SQL phát sinh thực tế, mức chờ khóa và mức tăng hiệu năng vẫn phải đo. Không suy từ CPU cao rằng đã xác định được điểm nghẽn, cũng không coi việc có khóa là lỗi: Pha 1 đã có cơ chế chống bán vượt ghế.

### Số liệu Kaggle Pha 1 đã có

Nguồn: [báo cáo Pha 1](../load-tests/README.md), [GET CSV](../load-tests/results/busbooking_baseline/baseline_summary.csv), [POST CSV](../load-tests/results/busbooking_baseline/booking_summary.csv) và [manifest](../load-tests/results/busbooking_baseline/manifest.json).

| Workload cũ tại 20 virtual users | Requests trong snapshot CSV | RPS | p95 | Java CPU trung bình | Java RSS tối đa |
|---|---:|---:|---:|---:|---:|
| GET danh sách/chi tiết chuyến, tỷ lệ 3:1 | 2.834 | 48,01 | 6 ms | 19,44% | 543,86 MiB |
| POST tạo booking | 2.789 | 47,21 | 25 ms | 83,02% | 643,30 MiB |

Cả hai CSV ghi 0 lỗi; báo cáo POST ghi 0 chuyến sai cân bằng ghế trong fixture. GET chỉ có 5 chuyến; POST dùng 1.000 chuyến × 4 ghế, một USER/JWT dùng chung, phân phối yêu cầu trên nhiều chuyến. Các lượt chạy dài 60 giây, có ramp-up, `wait_time=0,2–0,6 giây`, chưa tách warm-up. CPU trên là giá trị của tiến trình Java theo `psutil`, chưa chia số CPU logic; không phải phần trăm toàn bộ máy.

**Các số cũ là mốc tham khảo, không phải số đối chứng trực tiếp cho mọi bài Pha 2.** CSV khác thống kê console cuối lượt; manifest chưa ghi commit source tạo JAR; chưa có mẫu tài nguyên gốc để tính lại. Không lấy GET 6 ms so với một workload mới trên dữ liệu lớn, hoặc lấy POST 25 ms để tuyên bố đã giảm chờ khóa. Nhóm sẽ build lại đúng Pha 1 và chạy lại từng workload đối chứng trong cùng phiên Kaggle với bản cải tiến.

### Phạm vi được chốt

- Giữ A/B, nâng phần tách mô hình đọc trước đây từ optional thành phần chính của A để làm rõ thay đổi kiến trúc.
- Thay cache địa điểm của C bằng việc tách dữ liệu cần cho tạo booking khỏi mô hình Trip chi tiết. Phần này bám gợi ý về transaction/khóa trong README và dùng trực tiếp luồng POST đã có bài đo.
- Cache, outbox email, nhiều backend instance, CI/CD và tối ưu connection pool để ở hướng phát triển. Chúng không phải biến số trong thí nghiệm chính; bộ số liệu cũ cũng chưa chứng minh lợi ích của chúng.
- Mỗi người thực hiện một phần từ hiện trạng, thiết kế, code, test tới đo và báo cáo. A/B/C dùng chung môi trường và biểu mẫu. **B/C có giao điểm ở `BookingService.create`, A/C có giao điểm quanh Trip; không coi ba nhánh là hoàn toàn độc lập về code.**

## 2. Thiết kế trước và sau

| Luồng | Pha 1 | Pha 2 |
|---|---|---|
| Tìm chuyến | `TripController → TripService → TripRepository → entity + quan hệ → Trip → response`, trả toàn bộ kết quả | `TripController → use case tìm chuyến → TripSearchQuery → projection → TripSearchResult → response`, hỗ trợ giới hạn kết quả tại DB |
| Nhận POST đặt vé | Mỗi request đi thẳng vào luồng tạo booking | Kiểm tra/giành key trong transaction; request mới tạo booking, request trùng đọc lại kết quả |
| Dữ liệu dùng để tạo booking | Khóa Trip rồi mapper dựng Trip với thông tin tuyến/địa điểm/xe/nhà xe | `TripBookingRepository.lockForBooking → BookingTripSnapshot` từ scalar của Trip; kiểm tra và trừ ghế trong cùng transaction |

Đây là **tách trách nhiệm đọc/ghi trong cùng monolith và cùng DB**, không phải CQRS có DB đọc riêng hoặc đồng bộ bất đồng bộ. Mô hình đọc chứa dữ liệu màn hình cần; snapshot đặt vé chứa dữ liệu quyết định nghiệp vụ cần. Business chỉ biết các port và kiểu Java, không import HTTP DTO, JPA Entity, `Pageable`, JDBC hay Redis.

## 3. T4A — Đường đọc riêng cho tìm chuyến

**Người phụ trách: A.** Mục tiêu là giảm dữ liệu và công việc để phục vụ một trang kết quả tìm chuyến, đồng thời tách cách tối ưu đọc khỏi giao dịch đặt vé.

### 3.1. Fixture và baseline

1. Dựng dữ liệu có seed cố định, bắt đầu khoảng 50.000 chuyến. Ghi số tuyến, số chuyến/ngày, thời gian lưu dữ liệu và cách phân bố; chẳng hạn dữ liệu nhiều tuyến trong nhiều tháng, có tuyến đông khách. Chốt fixture trước khi đo bản cải tiến, không chỉ tăng dữ liệu đến khi Pha 1 chậm.
2. Chọn bộ lọc có 0 kết quả, 1–20 kết quả và trên 20 kết quả; thêm lọc chỉ ngày và không lọc để kiểm tra tính tương thích. Lưu số dòng khớp của từng bộ lọc. Không bắt buộc benchmark toàn bộ ma trận tổ hợp bộ lọc.
3. Chạy `ANALYZE`, lấy SQL thật và tham số của Hibernate, lưu `EXPLAIN (ANALYZE, BUFFERS)`. GET tải riêng endpoint danh sách; không gộp với endpoint chi tiết như bài cũ khi kết luận về tìm kiếm.

### 3.2. Các bước triển khai có thể so sánh riêng

| Bản | Thay đổi | Cặp dùng để giải thích kết quả |
|---|---|---|
| **P1** | Đúng source Pha 1 | Đối chứng gốc |
| **A1** | Chỉ thêm index được chọn từ query plan, migration Flyway mới | P1/A1: cùng SQL nghiệp vụ, bộ lọc và toàn bộ kết quả, đo riêng tác dụng index |
| **A2** | Bổ sung phân trang DB và thứ tự ổn định | Trong cùng A2, so không phân trang với `page=0&size=20`: cùng index, cùng thứ tự, đo riêng việc giới hạn kết quả |
| **A3** | Tách `TripSearchQuery`, `TripSearchResult`; dùng projection thay entity graph trong đường đọc | A2/A3: cùng index, bộ lọc, trang và JSON, đo riêng cách đọc; thêm P1/A3 để báo cáo thay đổi tổng |

- Index khởi đầu là ứng viên `trips(route_id, departure_time)`; cân nhắc cột `id` và index phục vụ tìm tuyến theo query plan. Không mặc định một index tốt cho mọi bộ lọc; không đổi biểu thức lọc cùng lúc trong phép đo chỉ-index.
- API thêm `page`, `size` tùy chọn. Không có cả hai thì giữ cách gọi cũ trả đầy đủ. Có ít nhất một tham số thì phần còn thiếu mặc định `page=0`, `size=20`; yêu cầu `page>=0`, `size=1..100`, trả 400 khi không hợp lệ. Kiểm tra giới hạn offset của adapter để page quá lớn không gây tràn số/500.
- A2/A3 dùng `departure_time, id` cho cả đường có và không phân trang. Không lấy 20 phần tử đầu của P1 làm chuẩn khi có chuyến trùng giờ, vì P1 chỉ sắp theo giờ. Cặp đo phân trang trong A2 giải quyết sai khác này.
- Response vẫn là mảng với các trường hiện có; adapter dùng giới hạn tại DB, không lấy toàn bộ rồi cắt bằng Java. Không thêm `COUNT(*)` chỉ để tạo `Page` nếu hợp đồng không cần tổng số dòng. Projection phải lấy đủ trường JSON hiện tại; không bỏ thông tin để làm kết quả nhanh hơn.
- Port đọc và kết quả không phụ thuộc JPA/HTTP. Phần ghi và khóa Trip cũ tiếp tục hoạt động; adapter query mới không thay chính sách ghế hay trạng thái chuyến.

### 3.3. Kiểm thử và nghiệm thu

Kiểm tra gọi cũ, đủ bộ lọc, biên ngày, chuyến trùng giờ, trang liên tiếp/trang rỗng và tham số sai. Với DB cố định, ghép các trang phải đúng tập ID, đúng thứ tự và không trùng/thiếu; A2/A3 phải khớp từng trường JSON. Kiểm tra SQL có giới hạn tại PostgreSQL và số dòng được lấy về.

**Bằng chứng bắt buộc:** query plan trước/sau, số dòng khớp/trả, byte response, số cột/kiểu dữ liệu đọc, p50/p95, RPS, lỗi và CPU/RSS. Với bộ lọc có `N>20`, trang đầu chỉ chuyển 20 chuyến từ DB sang ứng dụng và trả 20 chuyến cho client; số dòng DB thực sự quét vẫn xem trong query plan, không mặc định cũng chỉ là 20. Nếu projection/index chưa làm p95 tốt hơn thì ghi riêng lợi ích cấu trúc/dữ liệu và kết quả độ trễ thực tế, không gán mọi cải thiện cho projection.

**Vị trí code:** `TripController`, `TripService` hoặc use case tìm chuyến riêng, query port/result mới ở business, adapter query mới ở data, `SpringDataTripRepository`, mapper response và migration. Mở rộng `TripRepositoryAdapterTest`, test API tìm chuyến và `TripBookingIntegrationTest`.

## 4. T4B — Idempotency bền vững cho đặt vé

**Người phụ trách: B.** Tình huống chất lượng: server đã xử lý đặt vé nhưng client mất phản hồi hoặc gửi lại, kể cả hai request đồng thời. Yêu cầu là một ý định mua chỉ tạo một booking và trừ ghế một lần. Đây là bổ sung độ tin cậy, không phải sửa lỗi bán vượt ghế đã được Pha 1 bảo vệ.

### 4.1. Hợp đồng

| Request | Kết quả Pha 2 |
|---|---|
| Không có `Idempotency-Key` | Giữ hành vi Pha 1, tạo thành công trả 201 |
| User + key mới, payload hợp lệ | Tạo booking và trừ ghế một lần, trả 201 |
| Cùng user/key và cùng payload | Trả 200 với cùng `bookingId` và trạng thái hiện tại, kể cả booking đã hủy |
| Cùng user/key nhưng khác payload | 409 với mã lỗi riêng, chẳng hạn `IDEMPOTENCY_KEY_REUSED`, phân biệt với hết ghế |
| Hai user dùng cùng chuỗi key | Hai ý định độc lập |

Key có độ dài 1–128, dùng ký tự ASCII chữ/số và `._:-`; header có mặt nhưng rỗng/sai định dạng trả 400. Client dùng một key cho toàn bộ lần gửi của cùng ý định, tạo key mới khi thực sự mua lần khác. Trong phạm vi Pha 2, giữ key cùng vòng đời dữ liệu booking, chưa tự động hết hạn/xóa key.

### 4.2. Thiết kế giao dịch

1. Thêm bảng chứa `user_id`, `idempotency_key`, fingerprint và `booking_id`, unique `(user_id, idempotency_key)`, khóa ngoại tới user/booking. `booking_id` có thể rỗng lúc giành key trong transaction, nhưng luồng thành công phải gắn booking trước commit; lỗi tạo booking rollback cả key. Điều chỉnh cleanup/reset test theo thứ tự khóa ngoại.
2. Fingerprint từ biểu diễn chuẩn của `tripId, passengerName, passengerPhone, quantity` sau validation. Độc lập thứ tự JSON; không tự đổi quy tắc chuẩn hóa tên/số điện thoại so với Pha 1 hoặc ghép chuỗi thiếu phân định.
3. Giành key bằng `INSERT ... ON CONFLICT DO NOTHING` trong transaction `READ COMMITTED` được xác nhận ở DB. Khi không insert được, dùng **SELECT tiếp theo** để đọc key đã commit và so fingerprint. Không dựa vào snapshot của cùng câu INSERT để giả định đã nhìn thấy dòng của transaction khác; không bắt lỗi unique từ `saveAndFlush` rồi tiếp tục dùng một transaction đã lỗi.
4. Chỉ request giành được key mới đi vào khối tạo booking. Giữ transaction tạo booking/trừ ghế; request trùng không khóa Trip và không trừ ghế lại. Test cả khi request đầu commit, rollback và khi request chờ gặp timeout.
5. Controller lấy user từ JWT hiện có, nhận header và chọn 201/200 qua kết quả use case. DB nằm trong adapter; cập nhật CORS cho header mới và OpenAPI. Thống nhất với C ranh giới giữa khối nhận diện key và khối tạo booking.

### 4.3. Đo, test và nghiệm thu

- Workload không retry đo chi phí lần tạo đầu, cùng danh sách ý định và header trên P1/B.
- Workload retry: ví dụ 1.000 ý định mua một vé, 200 ý định gửi thêm một lần; gồm retry tuần tự và cặp đồng thời. Fixture dư ghế cho **cả 1.200 request của P1** để hết ghế không che mất booking trùng. Nếu tất cả ý định thành công, mục tiêu B là 1.000 booking và 1.000 ghế đã trừ; số P1 phải lấy từ DB sau chạy.
- Gán mã ý định vào tên hành khách giả lập và lưu ánh xạ trước chạy, để đối soát được cả bản P1 chưa hiểu key. Lưu request, booking, ý định thành công, booking/ghế thừa, p95 lần đầu/replay và lỗi theo loại; không chỉ so RPS hai workload có lượng ghi khác nhau.
- Test key trùng, khác payload, khác user, header sai, rollback rồi retry, đặt–hủy–retry. Test ghế cuối dùng hai ý định/key khác nhau; chạy lại test quyền sở hữu, hoàn ghế và rollback.

**Vị trí code:** `BookingController`, `BookingService`, business port và adapter cho key, migration, `SecurityConfig`, OpenAPI; mở rộng `BookingControllerTest`, `BookingServiceTest`, `TripBookingIntegrationTest`.

## 5. T4C — Đường ghi đặt vé chỉ đọc dữ liệu cần thiết

**Người phụ trách: C.** Đây là phần thay cho cache địa điểm. C không thay cơ chế chống trùng của B và không bỏ khóa để tăng tốc.

### 5.1. Vấn đề và giả thuyết cần kiểm chứng

Luồng hiện tại có thể đối chiếu tại [BookingService](../src/main/java/com/example/busbooking/business/service/BookingService.java), [TripRepositoryAdapter](../src/main/java/com/example/busbooking/data/adapter/TripRepositoryAdapter.java), [TripPersistenceMapper](../src/main/java/com/example/busbooking/data/mapper/TripPersistenceMapper.java) và [SpringDataTripRepository](../src/main/java/com/example/busbooking/data/repository/SpringDataTripRepository.java):

1. `BookingService.create` bắt đầu transaction và gọi `findByIdForUpdate`.
2. Repository khóa dòng Trip trước khi tải quan hệ. Adapter gọi mapper để dựng `Trip` chi tiết.
3. Mapper truy cập Route → origin/destination và Vehicle → Operator; các quan hệ được khai báo lazy. Công việc đọc và dựng mô hình này xảy ra sau khi đã khóa dòng Trip.
4. Luồng create chỉ sử dụng ID, trạng thái, ghế trống và giá; sau đó trừ ghế và lưu booking.

**Giả thuyết:** tách snapshot cho use case tạo booking sẽ loại bỏ truy vấn quan hệ không cần thiết và giảm công việc trong thời gian giữ khóa, từ đó có thể cải thiện độ trễ/CPU và tải đồng thời. Chưa ấn định số SELECT tiết kiệm hay phần trăm tăng tốc: xác nhận bằng SQL trace của P1 trước khi triển khai. Không gọi đây là N+1 của API tìm chuyến, vì GET hiện đã `JOIN FETCH`; vấn đề ở đường ghi.

### 5.2. Thay đổi thiết kế

- Thêm business port, chẳng hạn `TripBookingRepository`, trả `BookingTripSnapshot(id, status, price, availableSeats)` cho thao tác `lockForBooking`. Adapter dùng truy vấn khóa root Trip hiện có, chỉ đọc scalar và dựng snapshot; không gọi `TripPersistenceMapper.toDomain`, không chạm quan hệ.
- Port cung cấp thao tác giảm ghế có điều kiện cho create. Business vẫn kiểm tra trạng thái, đủ ghế, tính giá và tạo booking. Snapshot chỉ có giá trị trong transaction hiện tại; không cache hoặc dùng lại để quyết định một booking khác.
- Giữ khóa bi quan trên đúng dòng Trip và transaction bao quanh khóa → kiểm tra → giảm ghế → lưu booking → commit. Cả cập nhật chuyến và hủy booking vẫn phối hợp bằng khóa dòng này như Pha 1. Không đổi sang khóa cả graph, bỏ khóa hoặc tách trừ ghế sang transaction riêng.
- Chỉ chuyển **luồng tạo booking** sang port mới. Hủy booking vẫn cần sức chứa xe để hoàn ghế; quản trị Trip cũng cần dữ liệu riêng. Không thay mapper chung thành bản thiếu thông tin làm hỏng các use case đó.
- Không đồng thời đổi index, pool, JWT lookup, batching hay chính sách nghiệp vụ trong cặp P1/C. Sau tích hợp, khối tạo mới của B sử dụng đường ghi của C; replay của B không đi qua đường đó.

### 5.3. Kịch bản trước/sau trên Kaggle

1. **Trace nhỏ để xác định nguyên nhân:** cùng fixture sạch, gọi một số booking riêng biệt, lưu SQL theo transaction. Phân loại SQL xác thực user/role với SQL tạo booking. Xác nhận truy vấn vào `routes`, `locations`, `vehicles`, `bus_operators` phát sinh từ mapper; C phải loại bỏ chúng khỏi khối create. Không tính số gọi adapter là số câu SQL.
2. **Tải phân tán:** phát lại danh sách ý định không retry trên nhiều chuyến. Có lượt tham chiếu theo fixture cũ 1.000 chuyến × 4 ghế; dùng thêm fixture chính có sức chứa xe và ghế khởi đầu thống nhất để đối soát.
3. **Tải tập trung:** cùng số ý định nhưng tập trung từng đợt vào một/vài chuyến. Ví dụ fixture 100 chuyến × 40 ghế và 4.000 ý định, mỗi chuyến đúng 40 ý định mua một ghế; bản phân tán trộn toàn bộ danh sách, bản tập trung chạy các nhóm cùng chuyến. Giữ nguyên danh sách/seed giữa P1/C. Bảo đảm đủ ghế theo từng chuyến cho workload hiệu năng, tách bài cố ý hết ghế.
4. So **P1/C khi chưa bật idempotency** để thấy tác dụng của C. Sau merge, so **B/B+C với key mới** trên cùng workload nếu muốn đo lợi ích còn lại khi có idempotency; hai bản phải có cùng index/cấu hình và chỉ khác phần C. Không trộn replay vào thống kê lần tạo đầu.

**Chỉ số:** SELECT/booking và SQL theo nhóm bảng, p50/p95 API, RPS thành công, CPU Java/DB trên cùng lượng công việc, RSS, lỗi và cân bằng ghế. Lấy mẫu `pg_stat_activity`/`pg_locks` để hỗ trợ nhận diện chờ khóa; tỷ lệ mẫu chờ không phải p95 thời gian chờ, và thời gian gọi hàm khóa còn gồm thực thi SQL/truyền dữ liệu, không được ghi thành thời gian chờ khóa thuần.

**Nghiệm thu cấu trúc và đúng đắn:** không SELECT quan hệ chỉ để dựng Trip chi tiết trong create; giảm số SQL thực đo so với P1; giữ schema JSON, HTTP status và giá/quantity/số ghế theo từng ý định trên fixture cố định. Khi đối chiếu booking giữa hai lượt, ánh xạ theo mã ý định, không yêu cầu ID/code/thời điểm tự sinh giống nhau. Test ghế cuối, số lượng lớn hơn ghế trống, chuyến hủy, lỗi lưu booking rollback ghế; kiểm tra đặt đồng thời với hủy booking/cập nhật chuyến theo chính sách hiện có. Không có ghế âm, không thiếu hoàn ghế, không booking dở dang. Nếu SQL giảm nhưng p95/RPS chưa cải thiện vượt dao động, báo cáo đúng mức cải thiện hiệu quả truy cập dữ liệu, chưa kết luận tăng khả năng chịu tải.

**Vị trí code:** `BookingService.create`, business port/snapshot mới, adapter đường ghi mới và query khóa root Trip. Giữ `TripRepository.findByIdForUpdate` và mapper cũ cho use case còn cần. Mở rộng `BookingServiceTest`, `TripBookingIntegrationTest` và test quản trị liên quan.

## 6. Quy trình đo chung trên một cấu hình Kaggle CPU

### 6.1. Môi trường và artifact

Kế thừa [notebook Pha 1](../load-tests/notebook/busbooking-kaggle-cpu-test.ipynb) và [hướng dẫn chạy](../load-tests/scripts/load_testing.md): build JAR từ commit, đưa JAR/fixture lên Kaggle, chạy Java + PostgreSQL + Locust trong notebook CPU. **Không cần Docker bên trong Kaggle**; Docker vẫn phục vụ đóng gói và chạy local theo yêu cầu môn học.

- Lấy số chính thức của mọi cặp trên **cùng một phiên Kaggle CPU**, chỉ một backend và một bộ tạo tải chạy tại một thời điểm. Máy local dùng để phát triển và kiểm tra kịch bản.
- Ghim Java 21, PostgreSQL cùng phiên bản server, Locust/psutil, heap và pool cho mọi bản. Có thể bắt đầu `-Xms256m -Xmx1024m`, Hikari maximum pool 10; ghi cấu hình thực dùng. Kiểm tra PostgreSQL bằng `SHOW server_version`, không chỉ phiên bản client `psql`.
- Manifest ghi CPU/model/số CPU logic/RAM, JVM/DB settings, SHA source và trạng thái working tree khi build, SHA-256 JAR/fixture/script, seed, tải và thời gian. Nếu phiên Kaggle bị đổi, không ghép các bản khác phần cứng thành một cặp trước/sau.
- Restore **snapshot P1 sạch rồi áp dụng migration của bản được đo**. Không dùng snapshot đã có migration Pha 2 để chạy JAR P1; không sửa V1–V16. Đợi migration/index build hoàn tất rồi `ANALYZE`, warm-up và đo. Trước mỗi lượt POST, reset cả booking, ghế và bảng key nếu có; kiểm tra fixture bằng SQL.
- Chuẩn bị USER test/JWT trước khoảng đo, dùng nhiều tài khoản cố định cho workload chính; giữ một tài khoản trong lượt tái lập bài cũ. Không đưa login/OTP vào thời gian POST booking. Warm-up POST dùng chuyến riêng, không tiêu thụ ghế của fixture đo.

### 6.2. Hai mức đánh giá

| Mức | Cách chạy | Mục đích |
|---|---|---|
| **Tái lập tham khảo** | Chạy lại P1 theo script cũ: GET mix 3:1 với fixture nhỏ; POST theo fixture cũ; 20 users, wait 0,2–0,6 giây | Kiểm tra pipeline và liên hệ với báo cáo đã có; không dùng để kết luận mọi cải tiến |
| **Đối chứng chính** | P1 và từng bản thay đổi chạy cùng workload A/B/C mới, cấu hình và fixture cố định | Đánh giá đúng nguyên nhân và kết quả của từng thay đổi |

Script cũ với thời gian chờ trung bình khoảng 0,4 giây có thể giới hạn RPS quanh 50 ở 20 users khi API nhanh. Vì vậy bài hiệu năng A/C dùng thêm cấu hình **`wait_time=0`, 10 và 20 virtual users**, cố định giữa hai bản. Đây là tải có kiểm soát để so sánh, không phải bằng chứng đã tìm ra công suất tối đa. Chạy thử để xác nhận Locust không là tiến trình bị giới hạn CPU; không đổi công cụ/cấu hình riêng cho một phía.

GET: warm-up 60 giây, reset thống kê rồi đo 120 giây, lưu số mẫu. POST: warm-up riêng, phát lại hết danh sách ý định cố định và chờ request hoàn tất thay vì cắt giữa chừng theo 60 giây. B tách thống kê lần đầu/replay; C dùng lượng công việc cố định khi so chi phí CPU. Mỗi cặp lặp ba lần, đổi thứ tự trước/sau giữa các lượt.

### 6.3. Thu thập số liệu và đối soát

1. **API:** p50/p95, request hoàn tất, thành công nghiệp vụ, lỗi kỹ thuật, RPS, byte response. Tách endpoint, workload và lần tạo/replay; không chỉ đọc dòng Aggregated của mọi endpoint.
2. **SQL:** dùng `EXPLAIN (ANALYZE, BUFFERS)` cho A; dùng chênh lệch `pg_stat_statements.calls` theo DB/user/query cho A/C. Chuẩn bị extension/preload và restart PostgreSQL trước khi bắt đầu toàn bộ thí nghiệm; cấu hình thống kê giống nhau cho mọi bản. Nếu không dùng được extension, dùng cùng cơ chế đếm JDBC ở cả hai bản, ghi rõ artifact có instrumentation. SQL log chi tiết chỉ bật trong lượt trace, không bật riêng một bản trong benchmark.
3. **Tài nguyên:** lưu mẫu theo thời gian của Java, PostgreSQL và Locust, có timestamp gắn với khoảng đo. Với PostgreSQL tính cả nhóm tiến trình server/worker liên quan, tránh chỉ lấy tiến trình cha. Lưu CPU seconds cho lượt POST cố định; phân biệt CPU trung bình với CPU/booking, RSS với heap. Ghi đơn vị MiB và cách chuẩn hóa CPU.
4. **Dữ liệu:** gán `intent_id` vào dữ liệu hành khách giả lập và lưu danh sách đầu vào. Tính booking trùng theo số booking vượt quá một của mỗi ý định; tính ghế thừa so với quantity dự kiến của các ý định thành công. Kiểm tra thêm `available_seats + SUM(quantity của booking CONFIRMED) = sức chứa xe` theo chuyến với fixture ban đầu chưa có booking và ghế trống bằng sức chứa. Cân bằng ghế đúng không thay thế kiểm tra booking trùng.
5. **Thống kê cuối lượt:** chờ toàn bộ request hoàn tất và xuất thống kê cuối sau khi Locust dừng nhận công việc. Đối chiếu tổng request với danh sách đầu vào/log; không mặc định file CSV định kỳ là thống kê cuối. Lưu CSV, log và mẫu tài nguyên gốc để giải thích nếu lệch console.
6. **Kết luận:** trình bày từng lượt và trung vị p95/RPS kèm min–max; trung vị p95 không phải p95 gộp của tất cả request. Chỉ nhận cải thiện hiệu năng khi xu hướng lặp lại và đủ tách khỏi dao động quan sát; ba lượt không phải bảo đảm ý nghĩa thống kê. Mức giảm dữ liệu/SQL và độ đúng nghiệp vụ được báo cáo riêng, kể cả khi độ trễ không đổi.

### 6.4. Ma trận so sánh tối thiểu

| Câu hỏi | Cặp đo | Điều kiện giữ giống nhau | Kết quả cần lưu |
|---|---|---|---|
| Index có tác dụng gì? | P1/A1 | Bộ lọc, dữ liệu, toàn bộ dòng trả | ID, query plan, buffer, thời gian SQL, p95 |
| Giới hạn 20 chuyến tiết kiệm gì? | A2 không phân trang/A2 trang đầu | Index, bộ lọc, thứ tự `departure_time,id` | 20 ID đầu đúng, dòng đọc/trả, byte, p95/RPS |
| Tách mô hình đọc/projection có lợi gì? | A2/A3 | Cùng trang, index, JSON | Cột/entity đọc, SQL, p95/RPS, CPU/RSS |
| Tác động tổng của A? | P1/A3 | Cùng fixture/bộ lọc, cùng nhu cầu xem trang đầu | Client sắp kết quả đầy đủ của P1 theo `departure_time,id` để đối chiếu 20 ID đầu với A3; ghi tổng byte/công việc vì P1 còn tải toàn bộ kết quả |
| B thêm chi phí bao nhiêu? | P1/B không retry | Cùng ý định/key, ghế, tải | p95 lần đầu, SQL, RPS, booking thành công |
| B ngăn đặt trùng không? | P1/B có retry | Cùng danh sách ý định và request, đủ ghế | Booking/ghế thừa, ý định hoàn tất, p95 replay |
| C bỏ được công việc nào? | P1/C, không key | Cùng ý định, tải phân tán và tập trung, không hết ghế | SQL/booking theo bảng, p95/RPS, CPU seconds/booking, mẫu chờ khóa |
| Tích hợp có hồi quy không? | B/B+C cho POST mới; A3/bản tích hợp cho GET | Cùng workload tương ứng | Kết quả nghiệp vụ/JSON và hiệu năng; thêm kiểm tra replay sau tích hợp |

## 7. Phân công, kiểm thử và sản phẩm bàn giao

| Người | Phần chính phải tự thực hiện | Phần chung phụ trách chuẩn bị | Review chéo |
|---|---|---|---|
| **A** | A1/A2/A3, query port/result/adapter, fixture GET, query plan, test và báo cáo đường đọc | Build JAR, SHA/hash, sơ đồ kiến trúc và cấu hình chạy | Review C: xác nhận create không tải graph và vẫn khóa đúng dòng |
| **B** | Bảng key, giao dịch idempotency, API/CORS/OpenAPI, workload retry, test và SQL đối soát | Snapshot/reset DB và cấp số migration mới để không trùng | Review A: bộ lọc, thứ tự, phân trang và tương thích JSON |
| **C** | Port/snapshot/adapter tạo booking, trace SQL, hai workload POST, test và báo cáo chi phí đường ghi | Khung notebook, thu thập SQL/tài nguyên, xuất CSV/manifest | Review B: retry đồng thời, rollback, khác payload và quyền sở hữu |

B/C thống nhất chữ ký khối tạo booking ngay ngày 2: B phụ trách lớp bao idempotency và phản hồi tạo/replay, C phụ trách dữ liệu và xử lý của khối tạo mới. A/C thêm port/adapter chuyên biệt, tránh cùng sửa mapper Trip dùng chung. Khi merge phải review lại transaction, không chỉ giải quyết xung đột biên dịch.

Sản phẩm dự kiến đặt tại `load-tests/phase2/` cho script/notebook/fixture và `load-tests/results/phase2/<run_id>/` cho manifest, CSV, SQL, log, mẫu tài nguyên và bảng tổng hợp. Không ghi đè kết quả Pha 1. Mỗi phần báo cáo có: hạn chế và nguồn bằng chứng → tình huống chất lượng → sơ đồ trước/sau → quyết định thiết kế và đánh đổi → kiểm thử → kết quả đo → giới hạn.

Một dòng kết quả phải có: workload, dữ liệu/bộ lọc, tải, wait time, SHA/JAR trước–sau, đơn vị, ba lượt, chênh lệch và đường dẫn artifact. Có thể bàn giao bảng trống trước triển khai; không điền số kỳ vọng như kết quả đã đo. A/B/C mỗi người tự demo phần mình.

## 8. Lịch đề xuất — 10 ngày làm việc

| Mốc | A | B | C |
|---|---|---|---|
| **Ngày 1–2: bằng chứng và pipeline** | Build đúng P1, thiết kế fixture và bộ lọc GET | Snapshot/reset, thiết kế key và danh sách ý định | Trace SQL tạo booking P1, notebook một lượt thử xuyên suốt và lưu CSV |
| **Ngày 3: baseline mới** | Chạy P1 với workload A, lấy query plan | Chạy P1 với request retry, đối soát booking/ghế | Chạy P1 với POST phân tán/tập trung, lưu SQL và tài nguyên |
| **Ngày 4–6: triển khai** | Từng bước index, phân trang, query port/projection và test | Idempotency, test giao dịch/API và OpenAPI | Port/snapshot tạo booking, test SQL/ghế/rollback; chuẩn bị biểu đồ và báo cáo |
| **Ngày 7: review và tích hợp** | Review C, chốt A3 | Review A, merge/review giao dịch cùng C | Review B, kiểm tra B+C, chốt notebook/cấu hình |
| **Ngày 8: đo chính thức** | Chạy các cặp A | Chạy các cặp B | Chạy các cặp C; cả nhóm vận hành tuần tự trong cùng phiên Kaggle |
| **Ngày 9: dự phòng và hồi quy** | Kiểm tra GET bản tích hợp | Đối soát retry/ghế bản tích hợp | So B/B+C, hoàn thiện dữ liệu gốc, chạy lại lượt lỗi nếu cần |
| **Ngày 10: bàn giao** | Demo tìm trang đầu và giải thích tác dụng từng bước | Demo retry đồng thời chỉ có một booking | Demo SQL create trước/sau và tải tập trung; hoàn thiện báo cáo chung |

Nếu ngày 2 chưa chạy được pipeline hoặc trace không xác nhận giả thuyết C, phải điều chỉnh kế hoạch trước khi triển khai, không đợi tới ngày đo chính thức. Không bổ sung hạ tầng/kiến trúc khác trong lịch chính. Chuẩn bị báo cáo từ lúc có baseline; ngày 9 dành cho tích hợp, kiểm tra và dự phòng.

**Bản nộp chung:** repo công khai có commit của từng người; tài liệu quyết định/sơ đồ kiến trúc Pha 2, README cách chạy Docker, OpenAPI cập nhật, notebook Kaggle, dữ liệu giả lập và kết quả có thể đối soát. GET tìm chuyến/địa điểm vẫn công khai; GET xem booking và POST đặt vé có JWT, phân quyền và quyền sở hữu qua luồng hiện có, đáp ứng yêu cầu ít nhất một GET và một POST cần xác thực. Không đưa JPA/HTTP vào các port/mô hình nghiệp vụ mới. Chỉ ghi lợi ích đã có bằng chứng, không cam kết sẵn tăng tốc bao nhiêu phần trăm hoặc khả năng mở rộng nhiều instance.

## 9. Nguồn đối chiếu

- [Đề bài](2026.md), [README và gợi ý Pha 2](../README.md#gợi-ý-cải-tiến-cho-pha-2), [kiến trúc Pha 1](03-system-architecture.md), [thiết kế DB](02-database-design.md).
- [Mã nguồn Pha 1 tại commit đã chọn](https://github.com/BuiHuy16/Bus-booking-system/tree/fd6b5f3026412d2359d70bfad681fc0773c8bcae).
- [Báo cáo và giới hạn bằng chứng Pha 1](../load-tests/README.md), [notebook Kaggle](../load-tests/notebook/busbooking-kaggle-cpu-test.ipynb), [hướng dẫn tái lập](../load-tests/scripts/load_testing.md).
- PostgreSQL 16: [EXPLAIN](https://www.postgresql.org/docs/16/using-explain.html), [transaction isolation và ON CONFLICT](https://www.postgresql.org/docs/16/transaction-iso.html), [row-level locking](https://www.postgresql.org/docs/16/explicit-locking.html), [pg_stat_statements](https://www.postgresql.org/docs/16/pgstatstatements.html).
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html); [Locust — task và thời gian chờ](https://docs.locust.io/en/stable/writing-a-locustfile.html).
