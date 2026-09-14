package com.rolesync.authservice.exceptions;


public class ConflictException extends RuntimeException {
    public ConflictException(String message) {
        super(message);
    }
}
