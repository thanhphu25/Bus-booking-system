-- Trip search by departure day, alone or with a route, read the whole trips table in Phase 1.
-- Departure time leads so one index serves both searches; route_id is matched inside the index.
-- A generic plan of the catch-all search query cannot use it and keeps the Phase 1 sequential scan.
-- A route-leading index was rejected: its generic plan reads far more pages than that scan
-- for the date-only search.
SET LOCAL lock_timeout = '5s';
CREATE INDEX idx_trips_departure_time_route_id ON trips (departure_time, route_id);
