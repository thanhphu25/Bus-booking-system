package com.example.busbooking.business.service;

import com.example.busbooking.business.port.repository.BookingIdempotencyRepository;
import com.example.busbooking.business.port.repository.BookingRepository;
import com.example.busbooking.business.port.repository.TripRepository;
import com.example.busbooking.domain.enums.BookingStatus;
import com.example.busbooking.domain.enums.TripStatus;
import com.example.busbooking.domain.exception.*;
import com.example.busbooking.domain.model.Booking;
import com.example.busbooking.domain.model.Trip;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

@Service
public class BookingService {
    private final BookingRepository bookingRepository;
    private final TripRepository tripRepository;
    private final BookingIdempotencyRepository idempotencyRepository;

    public BookingService(BookingRepository bookingRepository, TripRepository tripRepository,
                          BookingIdempotencyRepository idempotencyRepository) {
        this.bookingRepository = bookingRepository;
        this.tripRepository = tripRepository;
        this.idempotencyRepository = idempotencyRepository;
    }

    @Transactional
    public Booking create(Long userId, Long tripId, String passengerName,
                          String passengerPhone, int quantity) {
        return createBooking(userId, tripId, passengerName, passengerPhone, quantity);
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public CreateResult create(Long userId, Long tripId, String passengerName,
                               String passengerPhone, int quantity, String key) {
        if (key == null) {
            return new CreateResult(createBooking(userId, tripId, passengerName, passengerPhone, quantity), false);
        }

        String fingerprint = fingerprint(tripId, passengerName, passengerPhone, quantity);
        if (idempotencyRepository.claim(userId, key, fingerprint)) {
            Booking booking = createBooking(userId, tripId, passengerName, passengerPhone, quantity);
            idempotencyRepository.complete(userId, key, booking.getId());
            return new CreateResult(booking, false);
        }

        // Use a new READ COMMITTED statement to see the winner after ON CONFLICT waited for it.
        var claim = idempotencyRepository.find(userId, key).orElseThrow();
        if (!fingerprint.equals(claim.fingerprint())) {
            throw new IdempotencyKeyReusedException();
        }
        Booking booking = bookingRepository.findById(claim.bookingId()).orElseThrow();
        return new CreateResult(booking, true);
    }

    public record CreateResult(Booking booking, boolean replayed) {}

    private static String fingerprint(Long tripId, String passengerName, String passengerPhone, int quantity) {
        byte[] name = passengerName.getBytes(StandardCharsets.UTF_8);
        byte[] phone = passengerPhone.getBytes(StandardCharsets.UTF_8);
        byte[] payload = ByteBuffer.allocate(Long.BYTES + 3 * Integer.BYTES + name.length + phone.length)
                .putLong(tripId).putInt(quantity)
                .putInt(name.length).put(name).putInt(phone.length).put(phone).array();
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(payload));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private Booking createBooking(Long userId, Long tripId, String passengerName,
                                  String passengerPhone, int quantity) {
        if (quantity <= 0) throw new BusinessException("Quantity must be greater than zero");
        Trip trip = tripRepository.findByIdForUpdate(tripId)
                .orElseThrow(() -> new ResourceNotFoundException("Trip not found with id: " + tripId));
        if (trip.getStatus() != TripStatus.SCHEDULED) {
            throw new BusinessException("Trip is not available for booking");
        }
        if (trip.getAvailableSeats() < quantity) {
            throw new InsufficientSeatsException("Not enough available seats");
        }
        if (!tripRepository.updateAvailableSeats(tripId, -quantity)) {
            throw new InsufficientSeatsException("Not enough available seats");
        }
        BigDecimal total = trip.getPrice().multiply(BigDecimal.valueOf(quantity));
        Booking booking = new Booking(null, "BK-" + UUID.randomUUID().toString().replace("-", "").substring(0, 20), userId, tripId,
                passengerName, passengerPhone, quantity, trip.getPrice(), total,
                BookingStatus.CONFIRMED, LocalDateTime.now());
        return bookingRepository.save(booking);
    }

    @Transactional(readOnly = true)
    public Booking get(Long userId, boolean admin, Long bookingId) {
        Booking booking = bookingRepository.findById(bookingId)
                .orElseThrow(() -> new ResourceNotFoundException("Booking not found with id: " + bookingId));
        verifyAccess(userId, admin, booking);
        return booking;
    }

    @Transactional(readOnly = true)
    public List<Booking> history(Long userId) {
        return bookingRepository.findByUserId(userId);
    }

    @Transactional(readOnly = true)
    public List<Booking> listForAdmin(Long userId, Long tripId, BookingStatus status) {
        return bookingRepository.findForAdmin(userId, tripId, status);
    }

    @Transactional
    public Booking cancel(Long userId, boolean admin, Long bookingId) {
        Booking booking = bookingRepository.findByIdForUpdate(bookingId)
                .orElseThrow(() -> new ResourceNotFoundException("Booking not found with id: " + bookingId));
        verifyAccess(userId, admin, booking);
        if (booking.getStatus() == BookingStatus.CANCELLED) {
            throw new BusinessException("Booking is already cancelled");
        }
        Trip trip = tripRepository.findByIdForUpdate(booking.getTripId())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Trip not found with id: " + booking.getTripId()));
        if (trip.getVehicle() == null
                || trip.getAvailableSeats() + booking.getQuantity() > trip.getVehicle().seatCapacity()) {
            throw new BusinessException("Unable to restore available seats");
        }
        if (!tripRepository.updateAvailableSeats(booking.getTripId(), booking.getQuantity())) {
            throw new BusinessException("Unable to restore available seats");
        }
        return bookingRepository.updateStatus(bookingId, BookingStatus.CANCELLED);
    }

    private void verifyAccess(Long userId, boolean admin, Booking booking) {
        if (!admin && !booking.getUserId().equals(userId)) {
            throw new ForbiddenOperationException("You do not have access to this booking");
        }
    }
}
