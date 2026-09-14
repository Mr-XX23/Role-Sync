package com.rolesync.authservice.services.admin;

import com.rolesync.authservice.models.AuthUserCredentials;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Who is a platform super admin (the RoleSync team running the Super Admin Console). auth-service
 * is the only place this is decided; other services ask it through the internal API.
 *
 * <p>An account qualifies only while all of these hold: its email is on the
 * {@code platform.super-admin-emails} allowlist, the email is verified (a verified phone does not
 * count) and the account is ACTIVE. The stored {@code role} column is never consulted, because
 * people pick it themselves when they register.
 */
@Component
@Slf4j
public class PlatformAdminPolicy {

    /** The {@code platformRole} sign-in answers carry for super admins. */
    public static final String SUPER_ADMIN = "SUPER_ADMIN";

    private final Set<String> allowlist;

    public PlatformAdminPolicy(@Value("${platform.super-admin-emails:}") String superAdminEmails) {
        this.allowlist = parse(superAdminEmails);
        if (allowlist.isEmpty()) {
            log.info("platform.super-admin-emails is empty: nobody can use the Super Admin Console");
        } else {
            log.info("{} platform super admin email(s) configured", allowlist.size());
        }
    }

    public boolean isSuperAdmin(AuthUserCredentials user) {
        return user != null
                && user.isEmailVerified()
                && user.getStatus() == AuthUserCredentials.Status.ACTIVE
                && user.getEmail() != null
                && allowlist.contains(normalize(user.getEmail()));
    }

    /** {@link #SUPER_ADMIN} for platform super admins, otherwise null. */
    public String platformRole(AuthUserCredentials user) {
        return isSuperAdmin(user) ? SUPER_ADMIN : null;
    }

    /** The allowlist as configured: trimmed, lower-cased, without blanks or repeats. */
    public List<String> configuredEmails() {
        return List.copyOf(allowlist);
    }

    private static Set<String> parse(String superAdminEmails) {
        Set<String> emails = new LinkedHashSet<>();
        if (superAdminEmails != null) {
            Arrays.stream(superAdminEmails.split(","))
                    .map(PlatformAdminPolicy::normalize)
                    .filter(email -> !email.isEmpty())
                    .forEach(emails::add);
        }
        return emails;
    }

    private static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
