package com.example.busbooking.api.controller;

import com.example.busbooking.api.dto.booking.*;
import com.example.busbooking.api.mapper.BookingDtoMapper;
import com.example.busbooking.business.service.BookingService;
import com.example.busbooking.domain.exception.ForbiddenOperationException;
import com.example.busbooking.exception.ErrorResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.List;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api")
@SecurityRequirement(name = "bearerAuth")
public class BookingController {
    private static final String IDEMPOTENCY_KEY = "Idempotency-Key";
    private static final String KEY_PATTERN = "^[A-Za-z0-9._:-]{1,128}$";
    private static final Pattern VALID_KEY = Pattern.compile(KEY_PATTERN);

    private final BookingService bookingService;
    private final BookingDtoMapper mapper;

    public BookingController(BookingService bookingService, BookingDtoMapper mapper) {
        this.bookingService = bookingService;
        this.mapper = mapper;
    }

    @PostMapping("/bookings")
    @Operation(summary = "Create a booking or replay an existing booking for the authenticated user")
    @ApiResponse(responseCode = "201", description = "Booking created",
            content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = BookingResponse.class)))
    @ApiResponse(responseCode = "200", description = "Existing booking with its current status",
            content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = BookingResponse.class)))
    @ApiResponse(responseCode = "400", description = "Invalid request or Idempotency-Key",
            content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "409", description = "IDEMPOTENCY_KEY_REUSED or INSUFFICIENT_SEATS",
            content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = ErrorResponse.class)))
    @ApiResponse(responseCode = "503", description = "BOOKING_CLAIM_TIMEOUT. Retry with the same key",
            content = @Content(mediaType = MediaType.APPLICATION_JSON_VALUE, schema = @Schema(implementation = ErrorResponse.class)))
    public ResponseEntity<BookingResponse> create(@Valid @RequestBody BookingRequest request,
                                                   @Parameter(description = "Reuse this key for the same purchase intent",
                                                           schema = @Schema(pattern = KEY_PATTERN, minLength = 1, maxLength = 128))
                                                   @RequestHeader(name = IDEMPOTENCY_KEY, required = false) String key,
                                                   Authentication authentication) {
        Long userId = userId(authentication);
        if (key != null && !VALID_KEY.matcher(key).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid Idempotency-Key");
        }
        var result = bookingService.create(
                userId, request.tripId(), request.passengerName(), request.passengerPhone(), request.quantity(), key);
        return ResponseEntity.status(result.replayed() ? HttpStatus.OK : HttpStatus.CREATED)
                .body(mapper.toResponse(result.booking()));
    }

    @GetMapping("/bookings/{bookingId}")
    public BookingResponse get(@PathVariable Long bookingId, Authentication authentication) {
        Long userId = userId(authentication);
        return mapper.toResponse(bookingService.get(userId, isAdmin(authentication), bookingId));
    }

    @DeleteMapping("/bookings/{bookingId}")
    public BookingResponse cancel(@PathVariable Long bookingId, Authentication authentication) {
        Long userId = userId(authentication);
        return mapper.toResponse(bookingService.cancel(userId, isAdmin(authentication), bookingId));
    }

    @GetMapping("/users/me/bookings")
    public List<BookingHistoryResponse> history(Authentication authentication) {
        return bookingService.history(userId(authentication)).stream()
                .map(mapper::toHistoryResponse).toList();
    }

    private Long userId(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            throw new ForbiddenOperationException("Authentication is required");
        }
        try {
            return Long.valueOf(authentication.getName());
        } catch (NumberFormatException ex) {
            throw new ForbiddenOperationException("Authenticated principal must contain a numeric user id");
        }
    }

    private boolean isAdmin(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()) || "ADMIN".equals(a.getAuthority())
                        || "ROLE_SUPER_ADMIN".equals(a.getAuthority()) || "SUPER_ADMIN".equals(a.getAuthority()));
    }
}
