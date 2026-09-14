package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.Workspace;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface WorkspaceRepository extends JpaRepository<Workspace, UUID> {
    /** Workspaces the profile owns, suspended ones included, oldest first. */
    @Query("SELECT w FROM Workspace w WHERE w.owner.profileId = :ownerProfileId ORDER BY w.createdAt ASC")
    List<Workspace> findByOwnerProfileId(@Param("ownerProfileId") UUID ownerProfileId);

    List<Workspace> findByIsActive(Boolean isActive);

    @Query("SELECT w.owner.profileId FROM Workspace w WHERE w.workspaceId = :workspaceId")
    java.util.Optional<UUID> findOwnerProfileId(@Param("workspaceId") UUID workspaceId);

    /**
     * The workspace row, locked until the surrounding transaction ends. Everything that adds an
     * active member (seat limit) or changes the plan or suspension takes it first.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT w FROM Workspace w WHERE w.workspaceId = :workspaceId")
    Optional<Workspace> lockById(@Param("workspaceId") UUID workspaceId);

    @Query("SELECT w FROM Workspace w JOIN FETCH w.owner WHERE w.workspaceId = :workspaceId")
    Optional<Workspace> findWithOwner(@Param("workspaceId") UUID workspaceId);

    long countByIsActive(Boolean isActive);

    /** Rows of (assigned plan id, or null for none, number of workspaces). */
    @Query("SELECT w.planId, COUNT(w) FROM Workspace w GROUP BY w.planId")
    List<Object[]> countByPlanId();

    @Query("SELECT w.createdAt FROM Workspace w WHERE w.createdAt >= :since")
    List<LocalDateTime> findCreatedAtSince(@Param("since") LocalDateTime since);
}
