package com.example.busbooking.data;

import com.example.busbooking.data.adapter.TripRepositoryAdapter;
import com.example.busbooking.data.entity.TripEntity;
import com.example.busbooking.data.mapper.TripPersistenceMapper;
import com.example.busbooking.data.repository.SpringDataTripRepository;
import com.example.busbooking.domain.model.Trip;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.time.LocalDate;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class TripRepositoryAdapterTest {

    @Mock
    private SpringDataTripRepository repository;

    @Mock
    private TripPersistenceMapper mapper;

    @Mock
    private Trip trip;

    @Test
    void search_withoutDatePassesBothDateBoundsAsNull() {
        when(repository.search(null, 2L, null, null, Pageable.unpaged())).thenReturn(List.of());
        TripRepositoryAdapter adapter = new TripRepositoryAdapter(repository, mapper);

        assertEquals(List.of(), adapter.search(null, 2L, null));

        verify(repository).search(null, 2L, null, null, Pageable.unpaged());
        verifyNoInteractions(mapper);
    }

    @Test
    void search_withDateUsesHalfOpenWholeDayRange() {
        TripEntity entity = mock(TripEntity.class);
        when(repository.search(eq(1L), eq(2L),
                eq(LocalDate.of(2026, 10, 25).atStartOfDay()),
                eq(LocalDate.of(2026, 10, 26).atStartOfDay()),
                eq(Pageable.unpaged())))
                .thenReturn(List.of(entity));
        when(mapper.toDomain(entity)).thenReturn(trip);
        TripRepositoryAdapter adapter = new TripRepositoryAdapter(repository, mapper);

        assertEquals(List.of(trip), adapter.search(1L, 2L, LocalDate.of(2026, 10, 25)));

        verify(mapper).toDomain(entity);
    }

    @Test
    void search_withPagePassesOffsetAndLimitToTheQuery() {
        TripEntity entity = mock(TripEntity.class);
        when(repository.search(1L, 2L,
                LocalDate.of(2026, 10, 25).atStartOfDay(),
                LocalDate.of(2026, 10, 26).atStartOfDay(),
                PageRequest.of(3, 20)))
                .thenReturn(List.of(entity));
        when(mapper.toDomain(entity)).thenReturn(trip);
        TripRepositoryAdapter adapter = new TripRepositoryAdapter(repository, mapper);

        assertEquals(List.of(trip), adapter.search(1L, 2L, LocalDate.of(2026, 10, 25), 3, 20));
    }

    @Test
    void search_withOffsetBeyondIntRangeReturnsEmptyPageWithoutQuerying() {
        TripRepositoryAdapter adapter = new TripRepositoryAdapter(repository, mapper);

        assertEquals(List.of(), adapter.search(null, null, null, Integer.MAX_VALUE, 100));
        assertEquals(List.of(), adapter.search(null, null, null, Integer.MAX_VALUE / 100 + 1, 100));

        verifyNoInteractions(repository, mapper);
    }

    @Test
    void search_withLargestIntOffsetStillQueries() {
        when(repository.search(null, null, null, null, PageRequest.of(Integer.MAX_VALUE, 1))).thenReturn(List.of());
        TripRepositoryAdapter adapter = new TripRepositoryAdapter(repository, mapper);

        assertEquals(List.of(), adapter.search(null, null, null, Integer.MAX_VALUE, 1));

        verify(repository).search(null, null, null, null, PageRequest.of(Integer.MAX_VALUE, 1));
    }
}
