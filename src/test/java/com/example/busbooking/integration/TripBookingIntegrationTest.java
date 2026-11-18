package com.example.busbooking.integration;

import com.example.busbooking.api.dto.booking.BookingResponse;
import com.example.busbooking.api.dto.trip.TripResponse;
import com.example.busbooking.business.service.BookingService;
import com.example.busbooking.security.JwtService;
import tools.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class TripBookingIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired JwtService jwt;
    @Autowired BookingService bookingService;
    @Autowired ObjectMapper json;
    @Autowired PlatformTransactionManager transactionManager;

    private final String fixture = "it_" + UUID.randomUUID().toString().replace("-", "").substring(0, 10);
    private Long userId;
    private Long otherUserId;
    private Long adminId;
    private Long originId;
    private Long destinationId;
    private Long routeId;
    private Long vehicleId;
    private Long tripId;

    @BeforeEach
    void seed() {
        String suffix = fixture + "_" + UUID.randomUUID().toString().replace("-", "").substring(0, 6);
        Long userRole = roleId("USER");
        Long adminRole = roleId("ADMIN");
        userId = insertUser("user_" + suffix + "@example.com", userRole);
        otherUserId = insertUser("other_" + suffix + "@example.com", userRole);
        adminId = insertUser("admin_" + suffix + "@example.com", adminRole);
        originId = insertLocation("Origin " + suffix);
        destinationId = insertLocation("Destination " + suffix);
        routeId = jdbc.queryForObject("""
                INSERT INTO routes (origin_id, destination_id, estimated_duration_minutes, status)
                VALUES (?, ?, 120, 'ACTIVE') RETURNING id
                """, Long.class, originId, destinationId);
        Long operatorId = jdbc.queryForObject("""
                INSERT INTO bus_operators (name, address, phone, email, status)
                VALUES (?, 'Test address', '0900000000', ?, 'ACTIVE') RETURNING id
                """, Long.class, "Operator " + suffix, "operator_" + suffix + "@example.com");
        vehicleId = jdbc.queryForObject("""
                INSERT INTO vehicles (operator_id, license_plate, vehicle_type, seat_capacity, status)
                VALUES (?, ?, 'SLEEPER', 10, 'ACTIVE') RETURNING id
                """, Long.class, operatorId, ("T-" + suffix.substring(0, Math.min(17, suffix.length()))).toUpperCase());
        tripId = insertTrip(LocalDateTime.of(2026, 10, 25, 8, 0), 4, "SCHEDULED");
    }

    @AfterEach
    void clean() {
        jdbc.update("DELETE FROM booking_idempotency_keys WHERE user_id IN (?, ?, ?)", userId, otherUserId, adminId);
        jdbc.update("DELETE FROM bookings WHERE user_id IN (?, ?, ?)", userId, otherUserId, adminId);
        jdbc.update("DELETE FROM trips WHERE route_id = ?", routeId);
        jdbc.update("DELETE FROM vehicles WHERE id = ?", vehicleId);
        jdbc.update("DELETE FROM bus_operators WHERE email LIKE ?", "operator_" + fixture + "%");
        jdbc.update("DELETE FROM routes WHERE id = ?", routeId);
        jdbc.update("DELETE FROM locations WHERE id IN (?, ?)", originId, destinationId);
        jdbc.update("DELETE FROM users WHERE id IN (?, ?, ?)", userId, otherUserId, adminId);
    }

    @Test
    @Order(1)
    void tripSearchSupportsFiltersWholeDateAndDetailedResponse() throws Exception {
        insertTrip(LocalDateTime.of(2026, 10, 25, 23, 59), 3, "SCHEDULED");
        insertTrip(LocalDateTime.of(2026, 10, 26, 0, 0), 2, "SCHEDULED");

        MvcResult result = mvc.perform(get("/api/trips")
                        .param("originId", originId.toString())
                        .param("destinationId", destinationId.toString())
                        .param("departureDate", "2026-10-25"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].departureTime").value("2026-10-25T08:00:00"))
                .andExpect(jsonPath("$[1].departureTime").value("2026-10-25T23:59:00"))
                .andExpect(jsonPath("$[0].route.origin").value(org.hamcrest.Matchers.startsWith("Origin " + fixture)))
                .andExpect(jsonPath("$[0].route.destination").value(org.hamcrest.Matchers.startsWith("Destination " + fixture)))
                .andExpect(jsonPath("$[0].vehicle.vehicleType").value("SLEEPER"))
                .andExpect(jsonPath("$[0].vehicle.operatorName").value(org.hamcrest.Matchers.startsWith("Operator " + fixture)))
                .andReturn();

        TripResponse[] trips = json.readValue(result.getResponse().getContentAsString(), TripResponse[].class);
        assertThat(trips[0].routeId()).isEqualTo(routeId);
        assertThat(trips[0].vehicleId()).isEqualTo(vehicleId);
    }

    @Test
    @Order(2)
    void tripSearchAndGetHandleEmptyInvalidAndMissingRequests() throws Exception {
        mvc.perform(get("/api/trips").param("originId", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("INVALID_REQUEST"));
        mvc.perform(get("/api/trips").param("departureDate", "2026-02-30"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/trips").param("originId", "999999999"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
        mvc.perform(get("/api/trips/" + (tripId + 999999)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("NOT_FOUND"));
    }

    @Test
    @Order(3)
    void bookingLifecyclePersistsValuesProtectsOwnershipAndRestoresSeats() throws Exception {
        String token = jwt.issue(userId).value();
        String body = """
                {"tripId":%d,"passengerName":"Nguyen Van A","passengerPhone":"0901234567","quantity":2}
                """.formatted(tripId);

        MvcResult created = mvc.perform(post("/api/bookings").header("Authorization", "Bearer " + token)
                        .contentType(APPLICATION_JSON).content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tripId").value(tripId))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.unitPrice").value(150000.00))
                .andExpect(jsonPath("$.totalAmount").value(300000.00))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andExpect(jsonPath("$.bookingCode").value(org.hamcrest.Matchers.hasLength(23)))
                .andReturn();
        BookingResponse booking = json.readValue(created.getResponse().getContentAsString(), BookingResponse.class);
        assertThat(jdbc.queryForObject("SELECT available_seats FROM trips WHERE id = ?", Integer.class, tripId)).isEqualTo(2);

        mvc.perform(get("/api/bookings/" + booking.id()).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.id").value(booking.id()));
        mvc.perform(get("/api/bookings/" + booking.id()).header("Authorization", "Bearer " + jwt.issue(otherUserId).value()))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/bookings/" + booking.id()).header("Authorization", "Bearer " + jwt.issue(adminId).value()))
                .andExpect(status().isOk());
        mvc.perform(get("/api/users/me/bookings").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].id").value(booking.id()));
        mvc.perform(delete("/api/bookings/" + booking.id()).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("CANCELLED"));
        assertThat(jdbc.queryForObject("SELECT available_seats FROM trips WHERE id = ?", Integer.class, tripId)).isEqualTo(4);
        mvc.perform(delete("/api/bookings/" + booking.id()).header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error").value("BUSINESS_ERROR"));
    }

    @Test
    @Order(4)
    void bookingRejectsMissingInvalidAuthValidationAndInsufficientSeats() throws Exception {
        String body = """
                {"tripId":%d,"passengerName":"A","passengerPhone":"0901234567","quantity":1}
                """.formatted(tripId);
        mvc.perform(post("/api/bookings").contentType(APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/bookings").header("Authorization", "Bearer invalid")
                        .contentType(APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/bookings").header("Authorization", "Bearer " + jwt.issue(userId).value())
                        .contentType(APPLICATION_JSON).content(body.replace("\"quantity\":1", "\"quantity\":0")))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error").value("VALIDATION_ERROR"));
        String tooMany = body.replace("\"quantity\":1", "\"quantity\":5");
        mvc.perform(post("/api/bookings").header("Authorization", "Bearer " + jwt.issue(userId).value())
                        .contentType(APPLICATION_JSON).content(tooMany))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.error").value("INSUFFICIENT_SEATS"));
        assertThat(jdbc.queryForObject("SELECT count(*) FROM bookings WHERE trip_id = ?", Long.class, tripId)).isZero();
        assertThat(jdbc.queryForObject("SELECT available_seats FROM trips WHERE id = ?", Integer.class, tripId)).isEqualTo(4);
    }

    @Test
    @Order(5)
    void concurrentRequestsCannotOversellSeats() throws Exception {
        jdbc.update("UPDATE trips SET available_seats = 1 WHERE id = ?", tripId);
        String body = """
                {"tripId":%d,"passengerName":"Concurrent","passengerPhone":"0901234567","quantity":1}
                """.formatted(tripId);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<MvcResult> first = pool.submit(() -> postBooking(userId, "first-intent", body).andReturn());
            Future<MvcResult> second = pool.submit(() -> postBooking(userId, "second-intent", body).andReturn());
            assertThat(List.of(first.get(20, TimeUnit.SECONDS).getResponse().getStatus(),
                    second.get(20, TimeUnit.SECONDS).getResponse().getStatus()))
                    .containsExactlyInAnyOrder(201, 409);
            assertBookingState(1, 0, 1);
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    @Order(6)
    void bookingSaveFailureRollsBackSeatReservation() {
        assertThatThrownBy(() -> bookingService.create(
                userId, tripId, " ", "0901234567", 1, "retry-after-failure"))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertBookingState(0, 4, 0);
        assertThat(bookingService.create(userId, tripId, "Passenger", "0901234567", 1, "retry-after-failure")
                .replayed()).isFalse();
        assertBookingState(1, 3, 1);
    }

    @Test
    void replayMatchesValidatedFieldsRegardlessOfJsonOrderAndReturnsCancelledBooking() throws Exception {
        String key = "Purchase.1:test_key";
        var created = postBooking(userId, key, bookingBody("A: B"))
                .andExpect(status().isCreated()).andReturn();
        long id = bookingId(created);

        String reordered = """
                {"quantity":1,"passengerPhone":"0901234567","passengerName":"A: B","tripId":%d}
                """.formatted(tripId);
        postBooking(userId, key, reordered)
                .andExpect(status().isOk()).andExpect(jsonPath("$.id").value(id));
        postBooking(userId, key, bookingBody("A:  B"))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.error").value("IDEMPOTENCY_KEY_REUSED"));
        var other = postBooking(otherUserId, key, reordered).andExpect(status().isCreated()).andReturn();
        assertThat(bookingId(other)).isNotEqualTo(id);
        assertBookingState(2, 2, 2);

        mvc.perform(delete("/api/bookings/" + id).header("Authorization", "Bearer " + jwt.issue(userId).value()))
                .andExpect(status().isOk());
        postBooking(userId, key, reordered).andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id)).andExpect(jsonPath("$.status").value("CANCELLED"));
        assertBookingState(2, 3, 2);
    }

    @Test
    void rejectsMalformedAndRepeatedHeadersWithoutWriting() throws Exception {
        for (String key : List.of("", " ", "abc/def", "café", "a".repeat(129))) {
            postBooking(userId, key, bookingBody("Passenger")).andExpect(status().isBadRequest());
        }
        mvc.perform(post("/api/bookings").header("Authorization", "Bearer " + jwt.issue(userId).value())
                        .header("Idempotency-Key", "first", "second")
                        .contentType(APPLICATION_JSON).content(bookingBody("Passenger")))
                .andExpect(status().isBadRequest());
        assertBookingState(0, 4, 0);
        postBooking(userId, "a".repeat(128), bookingBody("Passenger")).andExpect(status().isCreated());
        assertBookingState(1, 3, 1);
    }

    @Test
    void waitingDuplicateReplaysAfterWinnerCommits() throws Exception {
        BookingService.CreateResult winner = runWithWaitingRequest(false, 200, "Passenger");
        assertThat(winner.replayed()).isFalse();
        assertBookingState(1, 3, 1);
    }

    @Test
    void waitingDuplicateCanClaimAfterWinnerRollsBack() throws Exception {
        runWithWaitingRequest(true, 201, "Other passenger");
        assertThat(jdbc.queryForObject("SELECT passenger_name FROM bookings WHERE trip_id = ?", String.class, tripId))
                .isEqualTo("Other passenger");
        assertBookingState(1, 3, 1);
    }

    private BookingService.CreateResult runWithWaitingRequest(boolean rollBack, int expectedStatus, String passenger)
            throws Exception {
        String key = "concurrent-intent";
        String application = "booking_" + fixture;
        var ready = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var winner = pool.submit(() -> holdBooking(key, ready, release, rollBack));
            try {
                assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
                var waiter = pool.submit(() -> readCommitted().execute(status -> {
                    jdbc.queryForObject("SELECT set_config('application_name', ?, true)", String.class, application);
                    try {
                        return postBooking(userId, key, bookingBody(passenger)).andReturn();
                    } catch (Exception error) {
                        throw new IllegalStateException(error);
                    }
                }));
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
                boolean waiting = false;
                while (System.nanoTime() < deadline && !waiter.isDone()) {
                    waiting = Boolean.TRUE.equals(jdbc.queryForObject("""
                            SELECT EXISTS (SELECT FROM pg_stat_activity
                            WHERE application_name = ? AND wait_event_type = 'Lock')
                            """, Boolean.class, application));
                    if (waiting) break;
                    Thread.sleep(20);
                }
                assertThat(waiting).isTrue();
                release.countDown();
                MvcResult response = waiter.get(10, TimeUnit.SECONDS);
                var created = winner.get(10, TimeUnit.SECONDS);
                assertThat(response.getResponse().getStatus()).isEqualTo(expectedStatus);
                if (!rollBack) assertThat(bookingId(response)).isEqualTo(created.booking().getId());
                return created;
            } finally {
                release.countDown();
            }
        }
    }

    @Test
    void claimLockTimeoutReturns503AndCanBeRetried() throws Exception {
        String key = "timed-out-intent";
        var ready = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            var winner = pool.submit(() -> holdBooking(key, ready, release, false));
            try {
                assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
                readCommitted().executeWithoutResult(status -> {
                    jdbc.execute("SET LOCAL lock_timeout = '250ms'");
                    try {
                        postBooking(userId, key, bookingBody("Passenger")).andExpect(status().isServiceUnavailable())
                                .andExpect(jsonPath("$.error").value("BOOKING_CLAIM_TIMEOUT"));
                    } catch (Exception error) {
                        throw new IllegalStateException(error);
                    } finally {
                        status.setRollbackOnly();
                    }
                });
                assertBookingState(0, 4, 0);
            } finally {
                release.countDown();
            }
            long bookingId = winner.get(10, TimeUnit.SECONDS).booking().getId();
            postBooking(userId, key, bookingBody("Passenger")).andExpect(status().isOk())
                    .andExpect(jsonPath("$.id").value(bookingId));
            assertBookingState(1, 3, 1);
        }
    }

    private BookingService.CreateResult holdBooking(String key, CountDownLatch ready, CountDownLatch release, boolean rollBack) {
        return readCommitted().execute(status -> {
            assertThat(jdbc.queryForObject("SHOW transaction_isolation", String.class)).isEqualTo("read committed");
            var booking = bookingService.create(userId, tripId, "Passenger", "0901234567", 1, key);
            ready.countDown();
            try {
                assertThat(release.await(20, TimeUnit.SECONDS)).isTrue();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(error);
            }
            if (rollBack) status.setRollbackOnly();
            return booking;
        });
    }

    private TransactionTemplate readCommitted() {
        var transaction = new TransactionTemplate(transactionManager);
        transaction.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
        return transaction;
    }

    private ResultActions postBooking(Long owner, String key, String body) throws Exception {
        return mvc.perform(post("/api/bookings").header("Authorization", "Bearer " + jwt.issue(owner).value())
                .header("Idempotency-Key", key).contentType(APPLICATION_JSON).content(body));
    }

    private String bookingBody(String passenger) {
        return """
                {"tripId":%d,"passengerName":"%s","passengerPhone":"0901234567","quantity":1}
                """.formatted(tripId, passenger);
    }

    private long bookingId(MvcResult response) throws Exception {
        return json.readValue(response.getResponse().getContentAsString(), BookingResponse.class).id();
    }

    private void assertBookingState(long bookings, int seats, long keys) {
        assertThat(jdbc.queryForObject("SELECT available_seats FROM trips WHERE id = ?", Integer.class, tripId)).isEqualTo(seats);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM bookings WHERE trip_id = ?", Long.class, tripId)).isEqualTo(bookings);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM booking_idempotency_keys WHERE user_id IN (?, ?)",
                Long.class, userId, otherUserId)).isEqualTo(keys);
    }

    private Long roleId(String name) {
        return jdbc.queryForObject("SELECT id FROM roles WHERE name = ?", Long.class, name);
    }

    private Long insertUser(String email, Long roleId) {
        return jdbc.queryForObject("""
                INSERT INTO users (full_name, email, password, phone, role_id, status, email_verified)
                VALUES (?, ?, 'test-hash', '0900000000', ?, 'ACTIVE', TRUE) RETURNING id
                """, Long.class, email, email, roleId);
    }

    private Long insertLocation(String name) {
        return jdbc.queryForObject("""
                INSERT INTO locations (name, province, address)
                VALUES (?, 'Test Province', ?) RETURNING id
                """, Long.class, name, name + " address");
    }

    private Long insertTrip(LocalDateTime departure, int seats, String status) {
        return jdbc.queryForObject("""
                INSERT INTO trips (route_id, vehicle_id, departure_time, arrival_time, price, available_seats, status)
                VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id
                """, Long.class, routeId, vehicleId, departure, departure.plusHours(2),
                new BigDecimal("150000.00"), seats, status);
    }
}
