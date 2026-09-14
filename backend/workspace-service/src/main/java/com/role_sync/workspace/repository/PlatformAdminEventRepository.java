package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.PlatformAdminEvent;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface PlatformAdminEventRepository extends JpaRepository<PlatformAdminEvent, UUID> {

    /** Newest first. */
    @Query("SELECT e FROM PlatformAdminEvent e ORDER BY e.createdAt DESC, e.eventId DESC")
    List<PlatformAdminEvent> findRecent(Pageable page);
}
