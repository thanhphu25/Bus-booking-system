package com.example.busbooking.integration;

import com.example.busbooking.business.port.repository.TripRepository;
import com.example.busbooking.business.service.BookingService;
import com.example.busbooking.domain.enums.BookingStatus;
import com.example.busbooking.domain.model.Booking;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Phase 2C: the create-booking transaction must lock the Trip root row and read only its scalar columns.
 * Hibernate SQL is recorded to show that route/location/vehicle/operator are no longer queried while the lock is held.
 */
@SpringBootTest(properties =
        "spring.jpa.properties.hibernate.session_factory.statement_inspector="
                + "com.example.busbooking.integration.SqlRecorder")
@ActiveProfiles("test")
class BookingCreateSqlIntegrationTest {

    private static final Pattern RELATION_TABLES =
            Pattern.compile("\\b(routes|locations|vehicles|bus_operators)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern LOCK_CLAUSE =
            Pattern.compile("\\bfor (no key )?update\\b", Pattern.CASE_INSENSITIVE);

    @Autowired JdbcTemplate jdbc;
    @Autowired BookingService bookingService;
    @Autowired TripRepository tripRepository;
    @Autowired PlatformTransactionManager transactionManager;

    private final String suffix = "sql_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    private Long userId;
    private Long originId;
    private Long destinationId;
    private Long routeId;
    private Long operatorId;
    private Long vehicleId;
    private Long tripId;

    @BeforeEach
    void seed() {
        Long userRole = jdbc.queryForObject("SELECT id FROM roles WHERE name = 'USER'", Long.class);
        userId = jdbc.queryForObject("""
                INSERT INTO users (full_name, email, password, phone, role_id, status, email_verified)
                VALUES (?, ?, 'test-hash', '0900000000', ?, 'ACTIVE', TRUE) RETURNING id
                """, Long.class, suffix, suffix + "@example.com", userRole);
        originId = insertLocation("Origin " + suffix);
        destinationId = insertLocation("Destination " + suffix);
        routeId = jdbc.queryForObject("""
                INSERT INTO routes (origin_id, destination_id, estimated_duration_minutes, status)
                VALUES (?, ?, 120, 'ACTIVE') RETURNING id
                """, Long.class, originId, destinationId);
        operatorId = jdbc.queryForObject("""
                INSERT INTO bus_operators (name, address, phone, email, status)
                VALUES (?, 'Test address', '0900000000', ?, 'ACTIVE') RETURNING id
                """, Long.class, "Operator " + suffix, "operator_" + suffix + "@example.com");
        vehicleId = jdbc.queryForObject("""
                INSERT INTO vehicles (operator_id, license_plate, vehicle_type, seat_capacity, status)
                VALUES (?, ?, 'SLEEPER', 10, 'ACTIVE') RETURNING id
                """, Long.class, operatorId, ("S-" + suffix.substring(4, 16)).toUpperCase());
        LocalDateTime departure = LocalDateTime.of(2026, 12, 1, 8, 0);
        tripId = jdbc.queryForObject("""
                INSERT INTO trips (route_id, vehicle_id, departure_time, arrival_time, price, available_seats, status)
                VALUES (?, ?, ?, ?, ?, 10, 'SCHEDULED') RETURNING id
                """, Long.class, routeId, vehicleId, departure, departure.plusHours(2), new BigDecimal("150000.00"));
    }

    @AfterEach
    void clean() {
        jdbc.update("DELETE FROM bookings WHERE user_id = ?", userId);
        jdbc.update("DELETE FROM trips WHERE id = ?", tripId);
        jdbc.update("DELETE FROM vehicles WHERE id = ?", vehicleId);
        jdbc.update("DELETE FROM bus_operators WHERE id = ?", operatorId);
        jdbc.update("DELETE FROM routes WHERE id = ?", routeId);
        jdbc.update("DELETE FROM locations WHERE id IN (?, ?)", originId, destinationId);
        jdbc.update("DELETE FROM users WHERE id = ?", userId);
    }

    @Test
    void phase1DetailedLockStillLoadsRelationsForUseCasesThatNeedThem() {
        // Reference for P1 behaviour: cancel/admin still use the detailed Trip, which reads the relations.
        List<String> sql = recordInTransaction(() -> tripRepository.findByIdForUpdate(tripId).orElseThrow());

        assertThat(sql).anyMatch(statement -> LOCK_CLAUSE.matcher(statement).find());
        assertThat(sql).anyMatch(statement -> RELATION_TABLES.matcher(statement).find());
    }

    @Test
    void createLocksTripRootRowWithoutQueryingRelations() {
        List<String> sql = recordInTransaction(
                () -> bookingService.create(userId, tripId, "Passenger", "0901234567", 2));

        assertThat(sql).noneMatch(statement -> RELATION_TABLES.matcher(statement).find());
        List<String> lockStatements = sql.stream().filter(statement -> LOCK_CLAUSE.matcher(statement).find()).toList();
        assertThat(lockStatements).hasSize(1);
        assertThat(lockStatements.getFirst()).containsIgnoringCase("from trips");
        assertThat(sql).filteredOn(statement -> statement.toLowerCase().startsWith("select")).hasSize(1);
        assertThat(sql).anyMatch(statement -> statement.toLowerCase().startsWith("update trips"));
        assertThat(sql).anyMatch(statement -> statement.toLowerCase().startsWith("insert into bookings"));

        assertThat(jdbc.queryForObject("SELECT available_seats FROM trips WHERE id = ?", Integer.class, tripId))
                .isEqualTo(8);
        Booking booking = bookingService.history(userId).getFirst();
        assertThat(booking.getQuantity()).isEqualTo(2);
        assertThat(booking.getUnitPrice()).isEqualByComparingTo("150000.00");
        assertThat(booking.getTotalAmount()).isEqualByComparingTo("300000.00");
        assertThat(booking.getStatus()).isEqualTo(BookingStatus.CONFIRMED);
    }

    private List<String> recordInTransaction(Runnable action) {
        new TransactionTemplate(transactionManager).executeWithoutResult(status -> {
            SqlRecorder.clear();
            action.run();
        }); // commit (and its flush) happens before reading, so the whole transaction is recorded
        List<String> statements = SqlRecorder.statements();
        SqlRecorder.clear();
        return statements;
    }

    private Long insertLocation(String name) {
        return jdbc.queryForObject("""
                INSERT INTO locations (name, province, address)
                VALUES (?, 'Test Province', ?) RETURNING id
                """, Long.class, name, name + " address");
    }
}
