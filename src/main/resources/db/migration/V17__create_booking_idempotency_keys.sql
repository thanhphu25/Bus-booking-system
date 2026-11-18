CREATE TABLE booking_idempotency_keys (
    user_id BIGINT NOT NULL REFERENCES users(id),
    idempotency_key VARCHAR(128) NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    booking_id BIGINT REFERENCES bookings(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, idempotency_key),
    UNIQUE (booking_id)
);
