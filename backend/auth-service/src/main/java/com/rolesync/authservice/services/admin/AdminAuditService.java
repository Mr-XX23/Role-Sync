package com.rolesync.authservice.services.admin;

import com.rolesync.authservice.dto.admin.AdminAuditEntry;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.models.PlatformAdminEvent;
import com.rolesync.authservice.repository.PlatformAdminEventRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/** The audit trail of Super Admin Console actions taken through this service. */
@Service
@RequiredArgsConstructor
@Slf4j
public class AdminAuditService {

    static final int MAX_LIMIT = 500;
    static final int SUMMARY_MAX_LENGTH = 500;
    private static final int TARGET_LABEL_MAX_LENGTH = 255;

    private final PlatformAdminEventRepository events;

    /**
     * Records an action. Call it from the transaction that makes the change, so the change and its
     * audit row are saved together.
     */
    public PlatformAdminEvent record(AuthUserCredentials actor, String action, String targetType, String targetId,
                                     String targetLabel, String summary) {
        PlatformAdminEvent event = events.save(PlatformAdminEvent.builder()
                .actorUserId(actor.getAuthUserId())
                .actorEmail(actor.getEmail())
                .action(action)
                .targetType(targetType)
                .targetId(targetId)
                .targetLabel(truncate(targetLabel, TARGET_LABEL_MAX_LENGTH))
                .summary(truncate(summary, SUMMARY_MAX_LENGTH))
                .createdAt(LocalDateTime.now())
                .build());
        log.info("Platform admin {} {} {} {}", actor.getAuthUserId(), action, targetType, targetId);
        return event;
    }

    /** The latest entries, newest first ({@code limit} is kept within 1..500). */
    @Transactional(readOnly = true)
    public List<AdminAuditEntry> recent(int limit) {
        return events.findAllByOrderByCreatedAtDesc(PageRequest.of(0, Math.clamp(limit, 1, MAX_LIMIT))).stream()
                .map(AdminAuditEntry::of)
                .toList();
    }

    static String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        int end = maxLength - 1;
        if (Character.isHighSurrogate(value.charAt(end - 1))) {
            end--; // don't cut an emoji in half
        }
        return value.substring(0, end) + "…";
    }
}
