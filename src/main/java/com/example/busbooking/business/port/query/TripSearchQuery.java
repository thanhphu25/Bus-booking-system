package com.example.busbooking.business.port.query;

import com.example.busbooking.business.result.TripSearchResult;

import java.time.LocalDate;
import java.util.List;

public interface TripSearchQuery {
    List<TripSearchResult> search(
            Long originId,
            Long destinationId,
            LocalDate departureDate
    );

    List<TripSearchResult> search(
            Long originId,
            Long destinationId,
            LocalDate departureDate,
            int page,
            int size
    );
}
