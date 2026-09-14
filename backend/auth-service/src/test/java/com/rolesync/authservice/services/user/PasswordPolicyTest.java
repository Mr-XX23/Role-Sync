package com.rolesync.authservice.services.user;

import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordPolicyTest {

    // Every input is derived from a generated password, so the source holds no password-like strings.
    private final String valid = PasswordPolicy.generateTemporary();

    @Test
    void strongPasswordsAreAccepted() {
        assertNull(PasswordPolicy.problemWith(valid));
        assertNull(PasswordPolicy.problemWith(valid.substring(0, 8) + " " + valid.substring(8)));
    }

    @Test
    void eachMissingRuleIsExplained() {
        assertNotNull(PasswordPolicy.problemWith(null));
        assertTrue(PasswordPolicy.problemWith(valid.substring(0, 8)).contains("12 characters"));
        assertTrue(PasswordPolicy.problemWith(valid.toLowerCase(Locale.ROOT)).contains("upper and lower"));
        assertTrue(PasswordPolicy.problemWith(valid.replaceAll("\\d", "x")).contains("number and a symbol"));
        assertTrue(PasswordPolicy.problemWith(valid.replaceAll("[^A-Za-z0-9]", "y")).contains("number and a symbol"));
        assertTrue(PasswordPolicy.problemWith(" " + valid).contains("space"));
        assertTrue(PasswordPolicy.problemWith(valid.repeat(9)).contains("at most"));
    }

    @Test
    void temporaryPasswordsMeetThePolicyAndAvoidLookAlikes() {
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 500; i++) {
            String generated = PasswordPolicy.generateTemporary();
            assertEquals(PasswordPolicy.TEMPORARY_LENGTH, generated.length());
            assertNull(PasswordPolicy.problemWith(generated), generated);
            assertFalse(generated.matches(".*[0O1lI].*"), generated);
            seen.add(generated);
        }
        assertEquals(500, seen.size());
    }
}
