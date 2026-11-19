
SET TIME ZONE 'UTC';

INSERT INTO locations (name, province, address)
SELECT 'Station ' || lpad(n::text, 2, '0'), 'Province ' || lpad(n::text, 2, '0'), 'Address ' || lpad(n::text, 2, '0')
FROM generate_series(1, 40) AS n
ORDER BY n;

INSERT INTO bus_operators (name, address, phone, email, status, created_at)
SELECT 'Operator ' || lpad(n::text, 2, '0'), 'Operator address ' || lpad(n::text, 2, '0'),
       '09' || lpad(n::text, 8, '0'), 'operator' || lpad(n::text, 2, '0') || '@example.test',
       'ACTIVE', TIMESTAMP '2026-09-01 00:00:00'
FROM generate_series(1, 10) AS n
ORDER BY n;

INSERT INTO vehicles (operator_id, license_plate, vehicle_type, seat_capacity, status, created_at)
SELECT o.id, 'BENCHA' || lpad(n::text, 4, '0'),
       (ARRAY['SLEEPER', 'SEATER', 'LIMOUSINE'])[1 + mod(n, 3)],
       (ARRAY[40, 45, 9])[1 + mod(n, 3)],
       'ACTIVE', TIMESTAMP '2026-09-01 00:00:00'
FROM generate_series(1, 200) AS n
JOIN (SELECT id, row_number() OVER (ORDER BY id) AS rn FROM bus_operators) AS o ON o.rn = 1 + mod(n - 1, 10)
ORDER BY n;

INSERT INTO routes (origin_id, destination_id, estimated_duration_minutes, status)
SELECT o.id, d.id, 60 + mod(i * 13 + k * 29, 600), 'ACTIVE'
FROM generate_series(1, 40) AS i
CROSS JOIN generate_series(1, 3) AS k
JOIN (SELECT id, row_number() OVER (ORDER BY id) AS rn FROM locations) AS o ON o.rn = i
JOIN (SELECT id, row_number() OVER (ORDER BY id) AS rn FROM locations) AS d ON d.rn = 1 + mod(i - 1 + 7 * k, 40)
ORDER BY k, i;

INSERT INTO trips (route_id, vehicle_id, departure_time, arrival_time, price, available_seats, status, created_at)
WITH r AS (
    SELECT id, row_number() OVER (ORDER BY id) AS rn, estimated_duration_minutes AS duration FROM routes
), v AS (
    SELECT id, row_number() OVER (ORDER BY id) - 1 AS vn, seat_capacity FROM vehicles
), route_day AS (
    SELECT r.id AS route_id, r.rn, r.duration, d,
           ('x' || substr(md5(r.rn::text || ':' || d::text), 1, 7))::bit(28)::int AS h
    FROM r CROSS JOIN generate_series(0, 181) AS d
), slot AS (
    SELECT rd.*, k
    FROM route_day AS rd
    CROSS JOIN LATERAL generate_series(1, CASE WHEN rd.rn <= 3 THEN 36 + mod(rd.h, 9) ELSE mod(rd.h, 4) END) AS k
), timed AS (
    SELECT s.*, (DATE '2026-10-01' + s.d) + TIME '05:00' + make_interval(mins => 5 * mod(s.h + 37 * s.k, 216)) AS departure
    FROM slot AS s
)
SELECT t.route_id, v.id, t.departure, t.departure + make_interval(mins => t.duration),
       100000 + 10000 * mod(t.h + t.k, 30),
       mod(t.h + 7 * t.k, v.seat_capacity + 1),
       CASE WHEN mod(t.h + t.k, 25) = 0 THEN 'CANCELLED'
            WHEN t.departure < TIMESTAMP '2026-11-15 00:00:00' THEN 'COMPLETED'
            ELSE 'SCHEDULED' END,
       TIMESTAMP '2026-09-01 00:00:00'
FROM timed AS t
JOIN v ON v.vn = mod(t.rn * 31 + t.d * 7 + t.k, 200)
ORDER BY t.d, t.rn, t.k;
