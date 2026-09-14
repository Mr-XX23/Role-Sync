package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.WorkspaceMemberEvent;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface WorkspaceMemberEventRepository extends JpaRepository<WorkspaceMemberEvent, UUID> {

    /** Newest first. */
    List<WorkspaceMemberEvent> findByWorkspaceIdOrderByCreatedAtDesc(UUID workspaceId, Pageable page);
}
