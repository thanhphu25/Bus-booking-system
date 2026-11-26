package com.example.busbooking.data.adapter;

import com.example.busbooking.business.port.repository.BookingTripSnapshot;
import com.example.busbooking.business.port.repository.TripBookingRepository;
import com.example.busbooking.data.repository.SpringDataTripRepository;
import org.springframework.stereotype.Component;

import java.util.Optional;

@Component
public class TripBookingRepositoryAdapter implements TripBookingRepository {

    private final SpringDataTripRepository springDataTripRepository;

    public TripBookingRepositoryAdapter(SpringDataTripRepository springDataTripRepository) {
        this.springDataTripRepository = springDataTripRepository;
    }

    @Override
    public Optional<BookingTripSnapshot> lockForBooking(Long tripId) {
        // Same root-row locking query as Phase 1. Only scalar columns of trips are read; the lazy
        // route/vehicle associations stay uninitialized, so no extra SELECT runs while the lock is held.
        return springDataTripRepository.findByIdForUpdate(tripId)
                .map(entity -> new BookingTripSnapshot(entity.getId(), entity.getStatus(),
                        entity.getPrice(), entity.getAvailableSeats()));
    }

    @Override
    public boolean reserveSeats(Long tripId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be greater than zero");
        }
        return springDataTripRepository.updateAvailableSeats(tripId, -quantity) == 1;
    }
}
