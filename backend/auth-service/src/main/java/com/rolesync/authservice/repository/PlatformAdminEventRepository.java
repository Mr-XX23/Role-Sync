package com.rolesync.authservice.repository;

import com.rolesync.authservice.models.PlatformAdminEvent;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface PlatformAdminEventRepository extends JpaRepository<PlatformAdminEvent, UUID> {

    /** Newest first; the page size is the limit. */
    List<PlatformAdminEvent> findAllByOrderByCreatedAtDesc(Pageable pageable);
}
