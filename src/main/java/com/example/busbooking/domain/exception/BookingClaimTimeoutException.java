package com.example.busbooking.domain.exception;

public class BookingClaimTimeoutException extends RuntimeException {
    public BookingClaimTimeoutException(Throwable cause) {
        super("Booking idempotency claim was interrupted", cause);
    }
}
