package com.example.busbooking.business.port.repository;

import java.util.Optional;

public interface BookingIdempotencyRepository {
    boolean claim(Long userId, String key, String fingerprint);

    Optional<Claim> find(Long userId, String key);

    void complete(Long userId, String key, Long bookingId);

    record Claim(String fingerprint, Long bookingId) {}
}
