package com.example.busbooking.data.adapter;

import com.example.busbooking.business.port.repository.BookingIdempotencyRepository;
import com.example.busbooking.domain.exception.BookingClaimTimeoutException;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.jdbc.UncategorizedSQLException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public class BookingIdempotencyRepositoryAdapter implements BookingIdempotencyRepository {
    private final JdbcTemplate jdbc;

    public BookingIdempotencyRepositoryAdapter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public boolean claim(Long userId, String key, String fingerprint) {
        try {
            return jdbc.update("""
                    INSERT INTO booking_idempotency_keys (user_id, idempotency_key, fingerprint)
                    VALUES (?, ?, ?) ON CONFLICT (user_id, idempotency_key) DO NOTHING
                    """, userId, key, fingerprint) == 1;
        } catch (PessimisticLockingFailureException | QueryTimeoutException error) {
            throw new BookingClaimTimeoutException(error);
        } catch (UncategorizedSQLException error) {
            // Spring's default translator may leave PostgreSQL lock_timeout (55P03) uncategorized.
            String state = error.getSQLException().getSQLState();
            if ("55P03".equals(state) || "57014".equals(state)) {
                throw new BookingClaimTimeoutException(error);
            }
            throw error;
        }
    }

    @Override
    public Optional<Claim> find(Long userId, String key) {
        return jdbc.query("""
                SELECT fingerprint, booking_id FROM booking_idempotency_keys
                WHERE user_id = ? AND idempotency_key = ?
                """, (row, index) -> new Claim(row.getString("fingerprint"), row.getObject("booking_id", Long.class)),
                userId, key).stream().findFirst();
    }

    @Override
    public void complete(Long userId, String key, Long bookingId) {
        int updated = jdbc.update("""
                UPDATE booking_idempotency_keys SET booking_id = ?
                WHERE user_id = ? AND idempotency_key = ? AND booking_id IS NULL
                """, bookingId, userId, key);
        if (updated != 1) {
            throw new IllegalStateException("Booking idempotency claim was not completed");
        }
    }
}
