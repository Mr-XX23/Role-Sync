package com.rolesync.authservice.services.admin;

import com.rolesync.authservice.dto.admin.AdminStatsResponse;
import com.rolesync.authservice.dto.admin.DailyCount;
import com.rolesync.authservice.models.AuthUserCredentials.Status;
import com.rolesync.authservice.repository.AuthSecurityEventRepository;
import com.rolesync.authservice.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** Sign-in account numbers for the Super Admin Console overview. */
@Service
@RequiredArgsConstructor
public class AdminStatsService {

    static final int MAX_DAYS = 365;
    /** Successful password and Google sign-ins. */
    static final List<String> SIGN_IN_EVENTS = List.of("SUCCESSFUL_LOGIN", "OAUTH2_LOGIN");

    private final UserRepository userRepository;
    private final AuthSecurityEventRepository securityEventRepository;
    private final PlatformAdminPolicy policy;

    @Transactional(readOnly = true)
    public AdminStatsResponse stats(int days) {
        int range = Math.clamp(days, 1, MAX_DAYS);
        LocalDateTime now = LocalDateTime.now();

        Map<Status, Long> byStatus = new EnumMap<>(Status.class);
        long total = 0;
        for (Object[] row : userRepository.countAccountsByStatus()) {
            long count = ((Number) row[1]).longValue();
            total += count;
            if (row[0] instanceof Status status) {
                byStatus.merge(status, count, Long::sum);
            }
        }

        Map<String, Long> loginTypes = new LinkedHashMap<>();
        for (Object[] row : userRepository.countAccountsByLoginType()) {
            long count = ((Number) row[1]).longValue();
            if (row[0] instanceof Enum<?> type && count > 0) {
                loginTypes.merge(type.name(), count, Long::sum);
            }
        }

        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        LocalDate firstDay = today.minusDays(range - 1L);
        // Stored times are JVM-local; start a day early so every UTC day of the range is covered.
        LocalDateTime since = firstDay.minusDays(1).atStartOfDay();
        ZoneId storedIn = ZoneId.systemDefault();

        return AdminStatsResponse.builder()
                .totalUsers(total)
                .active(byStatus.getOrDefault(Status.ACTIVE, 0L))
                .inactive(byStatus.getOrDefault(Status.INACTIVE, 0L))
                .suspended(byStatus.getOrDefault(Status.SUSPENDED, 0L))
                .locked(byStatus.getOrDefault(Status.LOCKED, 0L))
                .emailVerified(userRepository.countEmailVerified())
                .newLast7Days(userRepository.countByCreatedAtGreaterThanEqual(now.minusDays(7)))
                .newLast30Days(userRepository.countByCreatedAtGreaterThanEqual(now.minusDays(30)))
                .loginTypes(loginTypes)
                .superAdminEmails(policy.configuredEmails())
                .signupsDaily(daily(userRepository.findCreatedAtSince(since), firstDay, today, storedIn))
                .signInsDaily(daily(securityEventRepository.findEventTimesSince(SIGN_IN_EVENTS, since), firstDay, today, storedIn))
                .build();
    }

    /** One entry per UTC day from firstDay to lastDay, oldest first, zero-filled. */
    static List<DailyCount> daily(List<LocalDateTime> times, LocalDate firstDay, LocalDate lastDay, ZoneId storedIn) {
        Map<LocalDate, Long> counts = new TreeMap<>();
        for (LocalDate day = firstDay; !day.isAfter(lastDay); day = day.plusDays(1)) {
            counts.put(day, 0L);
        }
        for (LocalDateTime time : times) {
            if (time != null) {
                LocalDate day = time.atZone(storedIn).withZoneSameInstant(ZoneOffset.UTC).toLocalDate();
                counts.computeIfPresent(day, (d, c) -> c + 1);
            }
        }
        List<DailyCount> result = new ArrayList<>(counts.size());
        counts.forEach((day, count) -> result.add(new DailyCount(day.toString(), count)));
        return result;
    }
}
