package com.rolesync.authservice.services.user;

import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Password rules for passwords people choose (change password) and the generator for the
 * temporary passwords workspace admins send. The frontend shows the same rules.
 */
public final class PasswordPolicy {

    public static final int MIN_LENGTH = 12;
    public static final int MAX_LENGTH = 128;
    public static final int TEMPORARY_LENGTH = 16;

    // No look-alike characters (0/O, 1/l/I), so a password copied from an email by eye still works.
    private static final String LOWER = "abcdefghijkmnpqrstuvwxyz";
    private static final String UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ";
    private static final String DIGITS = "23456789";
    private static final String SYMBOLS = "@$!%*?&";
    private static final String ALL = LOWER + UPPER + DIGITS + SYMBOLS;

    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordPolicy() {
    }

    /** Why the password is not acceptable, or null when it is. */
    public static String problemWith(String password) {
        if (password == null || password.length() < MIN_LENGTH) {
            return "Password must be at least " + MIN_LENGTH + " characters long.";
        }
        if (password.length() > MAX_LENGTH) {
            return "Password must be at most " + MAX_LENGTH + " characters long.";
        }
        if (!password.equals(password.strip())) {
            return "Password cannot start or end with a space.";
        }
        boolean lower = false;
        boolean upper = false;
        boolean digit = false;
        boolean symbol = false;
        for (char c : password.toCharArray()) {
            if (Character.isISOControl(c)) {
                return "Password cannot contain control characters.";
            }
            if (Character.isLowerCase(c)) {
                lower = true;
            } else if (Character.isUpperCase(c)) {
                upper = true;
            } else if (Character.isDigit(c)) {
                digit = true;
            } else if (!Character.isWhitespace(c)) {
                symbol = true;
            }
        }
        if (!lower || !upper) {
            return "Password must mix upper and lower case letters.";
        }
        if (!digit || !symbol) {
            return "Password must include a number and a symbol.";
        }
        return null;
    }

    /** A random temporary password that satisfies {@link #problemWith}. */
    public static String generateTemporary() {
        List<Character> chars = new ArrayList<>(TEMPORARY_LENGTH);
        chars.add(pick(LOWER));
        chars.add(pick(UPPER));
        chars.add(pick(DIGITS));
        chars.add(pick(SYMBOLS));
        while (chars.size() < TEMPORARY_LENGTH) {
            chars.add(pick(ALL));
        }
        Collections.shuffle(chars, RANDOM);
        StringBuilder password = new StringBuilder(TEMPORARY_LENGTH);
        chars.forEach(password::append);
        return password.toString();
    }

    private static char pick(String alphabet) {
        return alphabet.charAt(RANDOM.nextInt(alphabet.length()));
    }
}
