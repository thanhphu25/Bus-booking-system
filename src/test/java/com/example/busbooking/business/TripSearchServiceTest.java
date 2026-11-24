package com.example.busbooking.business;

import com.example.busbooking.business.port.query.TripSearchQuery;
import com.example.busbooking.business.result.TripSearchResult;
import com.example.busbooking.business.service.TripSearchService;
import com.example.busbooking.domain.enums.TripStatus;
import com.example.busbooking.domain.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class TripSearchServiceTest {

    @Mock
    private TripSearchQuery tripSearchQuery;

    @InjectMocks
    private TripSearchService tripSearchService;

    @Test
    void search_whenTripsExist_shouldReturnMatchingTrips() {
        LocalDate departureDate = LocalDate.of(2026, 10, 25);
        List<TripSearchResult> expectedTrips = List.of(result(7L));
        when(tripSearchQuery.search(1L, 2L, departureDate)).thenReturn(expectedTrips);

        assertEquals(expectedTrips, tripSearchService.search(1L, 2L, departureDate, null, null));

        verify(tripSearchQuery).search(1L, 2L, departureDate);
        verifyNoMoreInteractions(tripSearchQuery);
    }

    @Test
    void search_whenNoTripsExist_shouldReturnEmptyList() {
        LocalDate departureDate = LocalDate.of(2026, 10, 25);
        when(tripSearchQuery.search(1L, 2L, departureDate)).thenReturn(List.of());

        assertTrue(tripSearchService.search(1L, 2L, departureDate, null, null).isEmpty());
    }

    @Test
    void search_whenAllFiltersAreNull_shouldDelegateNullsWithoutChangingThem() {
        when(tripSearchQuery.search(null, null, null)).thenReturn(List.of());

        assertTrue(tripSearchService.search(null, null, null, null, null).isEmpty());

        verify(tripSearchQuery).search(null, null, null);
        verifyNoMoreInteractions(tripSearchQuery);
    }

    @Test
    void search_withOnlyOnePagingValue_shouldDefaultTheOther() {
        LocalDate departureDate = LocalDate.of(2026, 10, 25);
        List<TripSearchResult> page = List.of(result(7L));
        when(tripSearchQuery.search(1L, 2L, departureDate, 3, 20)).thenReturn(page);
        when(tripSearchQuery.search(1L, 2L, departureDate, 0, 5)).thenReturn(List.of());

        assertEquals(page, tripSearchService.search(1L, 2L, departureDate, 3, null));
        assertTrue(tripSearchService.search(1L, 2L, departureDate, null, 5).isEmpty());

        verify(tripSearchQuery).search(1L, 2L, departureDate, 3, 20);
        verify(tripSearchQuery).search(1L, 2L, departureDate, 0, 5);
        verifyNoMoreInteractions(tripSearchQuery);
    }

    @Test
    void search_withPageSizeLimits_shouldPassThemThrough() {
        when(tripSearchQuery.search(null, null, null, 0, 1)).thenReturn(List.of());
        when(tripSearchQuery.search(null, null, null, Integer.MAX_VALUE, 100)).thenReturn(List.of());

        assertTrue(tripSearchService.search(null, null, null, 0, 1).isEmpty());
        assertTrue(tripSearchService.search(null, null, null, Integer.MAX_VALUE, 100).isEmpty());

        verify(tripSearchQuery).search(null, null, null, 0, 1);
        verify(tripSearchQuery).search(null, null, null, Integer.MAX_VALUE, 100);
    }

    @Test
    void search_withInvalidPageOrSize_shouldRejectWithoutQuerying() {
        assertThrows(BusinessException.class, () -> tripSearchService.search(null, null, null, -1, null));
        assertThrows(BusinessException.class, () -> tripSearchService.search(null, null, null, -1, 20));
        assertThrows(BusinessException.class, () -> tripSearchService.search(null, null, null, null, 0));
        assertThrows(BusinessException.class, () -> tripSearchService.search(null, null, null, 0, -5));
        assertThrows(BusinessException.class, () -> tripSearchService.search(null, null, null, 0, 101));

        verifyNoInteractions(tripSearchQuery);
    }

    private static TripSearchResult result(Long id) {
        return new TripSearchResult(id, 1L, 2L, "Origin", "Destination", 120, "SLEEPER", 40, "Operator",
                LocalDateTime.of(2026, 10, 25, 8, 0), LocalDateTime.of(2026, 10, 25, 10, 0),
                new BigDecimal("150000.00"), 10, TripStatus.SCHEDULED);
    }
}
