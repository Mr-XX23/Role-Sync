package com.rolesync.authservice.configurations;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.rolesync.authservice.models.Role;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RoleDeserializerTest {

    @Test
    void everyRoleIsReadByNameIgnoringCaseAndSpaces() throws IOException {
        for (Role role : Role.values()) {
            assertEquals(role, read("\"  " + role.name().toLowerCase(Locale.ROOT) + " \""));
        }
        assertEquals(Role.SUPER_ADMIN, read("\"SuperAdmin\""));
    }

    @Test
    void anUnknownRoleIsRejectedWithTheRealRoleNames() {
        IllegalArgumentException error = assertThrows(IllegalArgumentException.class, () -> read("\"health_provider\""));

        String roles = Arrays.stream(Role.values()).map(Role::name).collect(Collectors.joining(", "));
        assertEquals("Invalid role: 'HEALTH_PROVIDER'. Valid roles are: " + roles, error.getMessage());
        assertFalse(error.getMessage().contains("HEALTHCARE"));
    }

    private static Role read(String json) throws IOException {
        try (JsonParser parser = new JsonFactory().createParser(json)) {
            parser.nextToken();
            return new RoleDeserializer().deserialize(parser, null);
        }
    }
}
