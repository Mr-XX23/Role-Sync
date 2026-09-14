package com.role_sync.billing.services;

import org.springframework.http.HttpStatus;

/** A refusal with a stable code the frontend and other services can act on. */
public class BillingException extends RuntimeException {

	public static final String OUT_OF_CREDITS = "OUT_OF_CREDITS";
	public static final String CREDITS_SUSPENDED = "CREDITS_SUSPENDED";
	public static final String INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE";
	public static final String INVALID_AMOUNT = "INVALID_AMOUNT";
	public static final String NOT_A_MEMBER = "NOT_A_MEMBER";

	private final HttpStatus status;
	private final String code;

	public BillingException(HttpStatus status, String code, String message) {
		super(message);
		this.status = status;
		this.code = code;
	}

	public HttpStatus status() {
		return status;
	}

	public String code() {
		return code;
	}
}
