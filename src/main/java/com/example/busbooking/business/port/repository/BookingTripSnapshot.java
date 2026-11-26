package com.example.busbooking.business.port.repository;

import com.example.busbooking.domain.enums.TripStatus;

import java.math.BigDecimal;

/**
 * Scalar state of a Trip row read while it is locked for creating a booking.
 * Valid only inside the transaction that obtained it; never cache or reuse it for another booking.
 */
public record BookingTripSnapshot(Long id, TripStatus status, BigDecimal price, int availableSeats) {
}
