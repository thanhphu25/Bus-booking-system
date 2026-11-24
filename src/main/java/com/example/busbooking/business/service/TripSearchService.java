package com.example.busbooking.business.service;

import com.example.busbooking.business.port.query.TripSearchQuery;
import com.example.busbooking.business.result.TripSearchResult;
import com.example.busbooking.domain.exception.BusinessException;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.util.List;

@Service
public class TripSearchService {

    private final TripSearchQuery tripSearchQuery;

    public TripSearchService(TripSearchQuery tripSearchQuery) {
        this.tripSearchQuery = tripSearchQuery;
    }

    // Without page and size the search returns every match, as in Phase 1.
    public List<TripSearchResult> search(
            Long originId,
            Long destinationId,
            LocalDate departureDate,
            Integer page,
            Integer size) {

        if (page == null && size == null) {
            return tripSearchQuery.search(originId, destinationId, departureDate);
        }
        int pageNumber = page == null ? 0 : page;
        int pageSize = size == null ? 20 : size;
        if (pageNumber < 0) throw new BusinessException("page must not be negative");
        if (pageSize < 1 || pageSize > 100) throw new BusinessException("size must be between 1 and 100");
        return tripSearchQuery.search(originId, destinationId, departureDate, pageNumber, pageSize);
    }
}
