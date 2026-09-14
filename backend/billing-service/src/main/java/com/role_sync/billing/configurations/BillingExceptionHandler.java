package com.role_sync.billing.configurations;

import com.role_sync.billing.payments.PaymentProviderException;
import com.role_sync.billing.services.BillingException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/** Turns failures into {@code {code, error}} bodies a UI can show without leaking internals. */
@RestControllerAdvice
public class BillingExceptionHandler {

	private static final Logger log = LoggerFactory.getLogger(BillingExceptionHandler.class);

	@ExceptionHandler(BillingException.class)
	public ResponseEntity<Map<String, String>> billing(BillingException ex) {
		return body(ex.status(), ex.code(), ex.getMessage());
	}

	@ExceptionHandler(ResponseStatusException.class)
	public ResponseEntity<Map<String, String>> status(ResponseStatusException ex) {
		HttpStatus status = HttpStatus.resolve(ex.getStatusCode().value());
		return body(status == null ? HttpStatus.INTERNAL_SERVER_ERROR : status, null,
				ex.getReason() == null ? "Request failed" : ex.getReason());
	}

	@ExceptionHandler(MethodArgumentNotValidException.class)
	public ResponseEntity<Map<String, String>> invalid(MethodArgumentNotValidException ex) {
		String detail = ex.getBindingResult().getFieldErrors().stream()
				.map(error -> error.getField() + ": " + error.getDefaultMessage())
				.collect(Collectors.joining("; "));
		return body(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", detail.isBlank() ? "Invalid request" : detail);
	}

	@ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
	public ResponseEntity<Map<String, String>> unreadable(Exception ex) {
		return body(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "The request could not be read. Check the values you sent.");
	}

	@ExceptionHandler(IllegalArgumentException.class)
	public ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException ex) {
		return body(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", ex.getMessage());
	}

	@ExceptionHandler(IllegalStateException.class)
	public ResponseEntity<Map<String, String>> conflict(IllegalStateException ex) {
		return body(HttpStatus.CONFLICT, "CONFLICT", ex.getMessage());
	}

	@ExceptionHandler(DataIntegrityViolationException.class)
	public ResponseEntity<Map<String, String>> duplicate(DataIntegrityViolationException ex) {
		log.warn("Rejected a write that broke a uniqueness rule: {}", ex.getMostSpecificCause().getMessage());
		return body(HttpStatus.CONFLICT, "DUPLICATE", "This was already recorded.");
	}

	@ExceptionHandler(PaymentProviderException.class)
	public ResponseEntity<Map<String, String>> provider(PaymentProviderException ex) {
		// The gateway failed us, not the caller, so this is a 502 rather than a 400.
		return body(HttpStatus.BAD_GATEWAY, "PAYMENT_PROVIDER_UNAVAILABLE", "The payment provider is unavailable. Try again shortly.");
	}

	private static ResponseEntity<Map<String, String>> body(HttpStatus status, String code, String message) {
		Map<String, String> body = new LinkedHashMap<>();
		if (code != null) {
			body.put("code", code);
		}
		body.put("error", message);
		return ResponseEntity.status(status).body(body);
	}
}
