-- Phase 2C fixture. Applied once to the clean P1 (V1-V16) snapshot; every trial restores that snapshot.
-- Password of all four users: Phase2FixtureOnly! (BCrypt hash below, fixture-only account).
INSERT INTO users (full_name, email, password, phone, role_id, status, email_verified)
SELECT 'Benchmark User ' || n, 'phase2-c-' || n || '@example.test',
       '$2a$10$8kBkggKZT8l6XxeMEIjhK.IHWS4.LbYr1dmBMr7pJhbE9T.GLMnca', '0900000000', id, 'ACTIVE', TRUE
FROM roles CROSS JOIN generate_series(1, 4) AS n WHERE name = 'USER';

INSERT INTO locations (name, province, address) VALUES
    ('Benchmark C Origin', 'Benchmark Province', 'Origin address'),
    ('Benchmark C Destination', 'Benchmark Province', 'Destination address');

INSERT INTO routes (origin_id, destination_id, estimated_duration_minutes, status)
SELECT origin.id, destination.id, 120, 'ACTIVE'
FROM locations AS origin CROSS JOIN locations AS destination
WHERE origin.name = 'Benchmark C Origin' AND destination.name = 'Benchmark C Destination';

INSERT INTO bus_operators (name, address, phone, email, status)
VALUES ('Benchmark C Operator', 'Operator address', '0900000000', 'operator-c@example.test', 'ACTIVE');

INSERT INTO vehicles (operator_id, license_plate, vehicle_type, seat_capacity, status)
SELECT id, plate, 'SLEEPER', capacity, 'ACTIVE'
FROM bus_operators CROSS JOIN (VALUES ('BENCH-C-04', 4), ('BENCH-C-40', 40)) AS v(plate, capacity)
WHERE name = 'Benchmark C Operator';

-- Legacy reference: trips 1..1000 with 4 seats (same shape as the Phase 1 POST fixture).
INSERT INTO trips (route_id, vehicle_id, departure_time, arrival_time, price, available_seats, status)
SELECT routes.id, vehicles.id, TIMESTAMP '2035-01-01 08:00:00' + n * INTERVAL '1 hour',
       TIMESTAMP '2035-01-01 10:00:00' + n * INTERVAL '1 hour', 150000, vehicles.seat_capacity, 'SCHEDULED'
FROM routes CROSS JOIN vehicles CROSS JOIN generate_series(1, 1000) AS n
WHERE vehicles.license_plate = 'BENCH-C-04'
ORDER BY n;

-- Main fixture: 100 measured trips with 40 seats, then 10 warm-up trips with 40 seats.
INSERT INTO trips (route_id, vehicle_id, departure_time, arrival_time, price, available_seats, status)
SELECT routes.id, vehicles.id, TIMESTAMP '2036-01-01 08:00:00' + n * INTERVAL '1 hour',
       TIMESTAMP '2036-01-01 10:00:00' + n * INTERVAL '1 hour', 150000, vehicles.seat_capacity, 'SCHEDULED'
FROM routes CROSS JOIN vehicles CROSS JOIN generate_series(1, 110) AS n
WHERE vehicles.license_plate = 'BENCH-C-40'
ORDER BY n;
