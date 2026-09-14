package com.rolesync.authservice.configurations;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.rolesync.authservice.models.Role;

import java.io.IOException;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

/**
 * Custom deserializer for the Role enum: accepts any role name regardless of case or surrounding
 * whitespace, plus "SUPERADMIN" as an alias for SUPER_ADMIN.
 */
public class RoleDeserializer extends JsonDeserializer<Role> {

    private static final String VALID_ROLES = Arrays.stream(Role.values())
            .map(Role::name)
            .collect(Collectors.joining(", "));

    @Override
    public Role deserialize(JsonParser parser, DeserializationContext context) throws IOException {
        String value = parser.getText().toUpperCase(Locale.ROOT).trim();

        if (value.equals("SUPERADMIN")) {
            return Role.SUPER_ADMIN;
        }
        try {
            return Role.valueOf(value);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException(
                    String.format("Invalid role: '%s'. Valid roles are: %s", value, VALID_ROLES));
        }
    }
}
