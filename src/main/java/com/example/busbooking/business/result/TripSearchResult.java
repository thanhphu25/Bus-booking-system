package com.example.busbooking.business.result;

import com.example.busbooking.domain.enums.TripStatus;

import java.math.BigDecimal;
import java.time.LocalDateTime;

// One trip of a search result, holding only what the search response shows.
public record TripSearchResult(
        Long id,
        Long routeId,
        Long vehicleId,
        String origin,
        String destination,
        int estimatedDurationMinutes,
        String vehicleType,
        int seatCapacity,
        String operatorName,
        LocalDateTime departureTime,
        LocalDateTime arrivalTime,
        BigDecimal price,
        int availableSeats,
        TripStatus status
) {
}
