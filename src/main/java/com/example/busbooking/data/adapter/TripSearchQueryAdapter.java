package com.example.busbooking.data.adapter;

import com.example.busbooking.business.port.query.TripSearchQuery;
import com.example.busbooking.business.result.TripSearchResult;
import com.example.busbooking.data.repository.SpringDataTripRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Component;

import java.time.LocalDate;
import java.util.List;

@Component
public class TripSearchQueryAdapter implements TripSearchQuery {

    private final SpringDataTripRepository springDataTripRepository;

    public TripSearchQueryAdapter(SpringDataTripRepository springDataTripRepository) {
        this.springDataTripRepository = springDataTripRepository;
    }

    @Override
    public List<TripSearchResult> search(
            Long originId,
            Long destinationId,
            LocalDate departureDate) {

        return search(originId, destinationId, departureDate, Pageable.unpaged());
    }

    @Override
    public List<TripSearchResult> search(
            Long originId,
            Long destinationId,
            LocalDate departureDate,
            int page,
            int size) {

        // JPA offsets are ints. A larger offset is far past any search result here,
        // so answer with an empty page instead of failing on the conversion.
        if ((long) page * size > Integer.MAX_VALUE) {
            return List.of();
        }
        return search(originId, destinationId, departureDate, PageRequest.of(page, size));
    }

    private List<TripSearchResult> search(
            Long originId,
            Long destinationId,
            LocalDate departureDate,
            Pageable pageable) {

        return springDataTripRepository.search(
                originId,
                destinationId,
                departureDate == null ? null : departureDate.atStartOfDay(),
                departureDate == null ? null : departureDate.plusDays(1).atStartOfDay(),
                pageable
        );
    }
}
