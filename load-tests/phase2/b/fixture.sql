INSERT INTO users (full_name, email, password, phone, role_id, status, email_verified)
SELECT 'Benchmark User ' || n, 'phase2-b-' || n || '@example.test',
       '$2a$10$8kBkggKZT8l6XxeMEIjhK.IHWS4.LbYr1dmBMr7pJhbE9T.GLMnca', '0900000000', id, 'ACTIVE', TRUE
FROM roles CROSS JOIN generate_series(1, 4) AS n WHERE name = 'USER';

INSERT INTO locations (name, province, address) VALUES
    ('Benchmark Origin', 'Benchmark Province', 'Origin address'),
    ('Benchmark Destination', 'Benchmark Province', 'Destination address');

INSERT INTO routes (origin_id, destination_id, estimated_duration_minutes, status)
SELECT origin.id, destination.id, 120, 'ACTIVE'
FROM locations AS origin CROSS JOIN locations AS destination
WHERE origin.name = 'Benchmark Origin' AND destination.name = 'Benchmark Destination';

INSERT INTO bus_operators (name, address, phone, email, status)
VALUES ('Benchmark Operator', 'Operator address', '0900000000', 'operator@example.test', 'ACTIVE');

INSERT INTO vehicles (operator_id, license_plate, vehicle_type, seat_capacity, status)
SELECT id, 'BENCH-B-01', 'SLEEPER', 4, 'ACTIVE' FROM bus_operators WHERE name = 'Benchmark Operator';

-- Trips 1..1000 are measured and 1001..1100 are reserved for warm-up.
INSERT INTO trips (route_id, vehicle_id, departure_time, arrival_time, price, available_seats, status)
SELECT routes.id, vehicles.id, TIMESTAMP '2035-01-01 08:00:00' + n * INTERVAL '1 hour',
       TIMESTAMP '2035-01-01 10:00:00' + n * INTERVAL '1 hour', 150000, vehicles.seat_capacity, 'SCHEDULED'
FROM routes CROSS JOIN vehicles CROSS JOIN generate_series(1, 1100) AS n
ORDER BY n;
