package com.example.busbooking.data;

import com.example.busbooking.business.result.TripSearchResult;
import com.example.busbooking.data.adapter.TripSearchQueryAdapter;
import com.example.busbooking.data.repository.SpringDataTripRepository;
import com.example.busbooking.domain.enums.TripStatus;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class TripSearchQueryAdapterTest {

    @Mock
    private SpringDataTripRepository repository;

    private final TripSearchResult trip = new TripSearchResult(7L, 1L, 2L, "Origin", "Destination", 120,
            "SLEEPER", 40, "Operator", LocalDateTime.of(2026, 10, 25, 8, 0), LocalDateTime.of(2026, 10, 25, 10, 0),
            new BigDecimal("150000.00"), 10, TripStatus.SCHEDULED);

    @Test
    void search_withoutDatePassesBothDateBoundsAsNull() {
        when(repository.search(null, 2L, null, null, Pageable.unpaged())).thenReturn(List.of());
        TripSearchQueryAdapter adapter = new TripSearchQueryAdapter(repository);

        assertEquals(List.of(), adapter.search(null, 2L, null));

        verify(repository).search(null, 2L, null, null, Pageable.unpaged());
    }

    @Test
    void search_withDateUsesHalfOpenWholeDayRange() {
        when(repository.search(1L, 2L,
                LocalDate.of(2026, 10, 25).atStartOfDay(),
                LocalDate.of(2026, 10, 26).atStartOfDay(),
                Pageable.unpaged()))
                .thenReturn(List.of(trip));
        TripSearchQueryAdapter adapter = new TripSearchQueryAdapter(repository);

        assertEquals(List.of(trip), adapter.search(1L, 2L, LocalDate.of(2026, 10, 25)));
    }

    @Test
    void search_withPagePassesOffsetAndLimitToTheQuery() {
        when(repository.search(1L, 2L,
                LocalDate.of(2026, 10, 25).atStartOfDay(),
                LocalDate.of(2026, 10, 26).atStartOfDay(),
                PageRequest.of(3, 20)))
                .thenReturn(List.of(trip));
        TripSearchQueryAdapter adapter = new TripSearchQueryAdapter(repository);

        assertEquals(List.of(trip), adapter.search(1L, 2L, LocalDate.of(2026, 10, 25), 3, 20));
    }

    @Test
    void search_withOffsetBeyondIntRangeReturnsEmptyPageWithoutQuerying() {
        TripSearchQueryAdapter adapter = new TripSearchQueryAdapter(repository);

        assertEquals(List.of(), adapter.search(null, null, null, Integer.MAX_VALUE, 100));
        assertEquals(List.of(), adapter.search(null, null, null, Integer.MAX_VALUE / 100 + 1, 100));

        verifyNoInteractions(repository);
    }

    @Test
    void search_withLargestIntOffsetStillQueries() {
        when(repository.search(null, null, null, null, PageRequest.of(Integer.MAX_VALUE, 1))).thenReturn(List.of());
        TripSearchQueryAdapter adapter = new TripSearchQueryAdapter(repository);

        assertEquals(List.of(), adapter.search(null, null, null, Integer.MAX_VALUE, 1));

        verify(repository).search(null, null, null, null, PageRequest.of(Integer.MAX_VALUE, 1));
    }
}
