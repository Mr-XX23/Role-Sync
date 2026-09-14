package com.rolesync.authservice.repository;

import com.rolesync.authservice.models.AuthSecurityEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

@Repository
public interface AuthSecurityEventRepository extends JpaRepository<AuthSecurityEvent, UUID> {

    List<AuthSecurityEvent> findTop20ByAuthUser_AuthUserIdOrderByEventTimeDesc(UUID authUserId);

    @Query("SELECT e.eventTime FROM AuthSecurityEvent e WHERE e.eventType IN :eventTypes AND e.eventTime >= :since")
    List<LocalDateTime> findEventTimesSince(@Param("eventTypes") Collection<String> eventTypes,
                                            @Param("since") LocalDateTime since);
}
