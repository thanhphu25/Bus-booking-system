package com.example.busbooking.business.port.repository;

import java.util.Optional;

/**
 * Write-path port for creating bookings. Unlike {@link TripRepository#findByIdForUpdate}, it exposes only the
 * Trip data needed to decide a booking, so route/location/vehicle/operator are not loaded while the row is locked.
 */
public interface TripBookingRepository {

    /** Locks the Trip row (SELECT ... FOR UPDATE) for the current transaction and returns its scalar state. */
    Optional<BookingTripSnapshot> lockForBooking(Long tripId);

    /** Conditionally decreases available seats; returns false when the trip would go below zero seats. */
    boolean reserveSeats(Long tripId, int quantity);
}
