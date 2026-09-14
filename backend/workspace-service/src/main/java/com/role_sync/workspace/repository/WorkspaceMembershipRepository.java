package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.Workspace;
import com.role_sync.workspace.models.WorkspaceMembership;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface WorkspaceMembershipRepository extends JpaRepository<WorkspaceMembership, UUID> {
    List<WorkspaceMembership> findByWorkspaceWorkspaceId(UUID workspaceId);
    List<WorkspaceMembership> findByProfileProfileId(UUID profileId);

    /** The profile's active workspaces, the one they joined first leading (their default). */
    @Query("SELECT wm.workspace FROM WorkspaceMembership wm WHERE wm.profile.profileId = :profileId AND wm.isActive = true " +
           "ORDER BY wm.joinedAt ASC")
    List<Workspace> findActiveWorkspacesByProfileId(@Param("profileId") UUID profileId);

    /** Every membership of a workspace (active or not) with its profile and role, oldest first. */
    @Query("SELECT wm FROM WorkspaceMembership wm JOIN FETCH wm.profile JOIN FETCH wm.role " +
           "WHERE wm.workspace.workspaceId = :workspaceId ORDER BY wm.joinedAt ASC")
    List<WorkspaceMembership> findMembersOfWorkspace(@Param("workspaceId") UUID workspaceId);

    @Query("SELECT wm FROM WorkspaceMembership wm JOIN FETCH wm.profile JOIN FETCH wm.role JOIN FETCH wm.workspace " +
           "WHERE wm.membershipId = :membershipId")
    Optional<WorkspaceMembership> findWithProfileAndRole(@Param("membershipId") UUID membershipId);

    @Query("SELECT wm FROM WorkspaceMembership wm JOIN FETCH wm.workspace w WHERE wm.profile.profileId = :profileId AND wm.isActive = true")
    List<WorkspaceMembership> findActiveMembershipsWithWorkspace(@Param("profileId") UUID profileId);

    Optional<WorkspaceMembership> findByWorkspaceWorkspaceIdAndProfileProfileId(UUID workspaceId, UUID profileId);

    // --- Authorization projections (resolved as SQL joins; no lazy-proxy navigation) ---

    /** An active membership's role and whether its workspace is active (not suspended). */
    interface ActiveMembershipView {
        String getRoleName();

        Boolean getWorkspaceActive();
    }

    @Query("SELECT wm.role.roleName AS roleName, wm.workspace.isActive AS workspaceActive FROM WorkspaceMembership wm " +
           "WHERE wm.workspace.workspaceId = :workspaceId AND wm.profile.profileId = :profileId AND wm.isActive = true")
    Optional<ActiveMembershipView> findActiveMembership(@Param("workspaceId") UUID workspaceId,
                                                        @Param("profileId") UUID profileId);

    /** Rows of (workspace id, role name) for the profile's active memberships. */
    @Query("SELECT wm.workspace.workspaceId, wm.role.roleName FROM WorkspaceMembership wm " +
           "WHERE wm.profile.profileId = :profileId AND wm.isActive = true")
    List<Object[]> findActiveRolesByProfileId(@Param("profileId") UUID profileId);

    @Query("SELECT wm.workspace.workspaceId FROM WorkspaceMembership wm WHERE wm.membershipId = :membershipId")
    Optional<UUID> findWorkspaceIdByMembershipId(@Param("membershipId") UUID membershipId);

    @Query("SELECT wm.profile.profileId FROM WorkspaceMembership wm WHERE wm.membershipId = :membershipId")
    Optional<UUID> findProfileIdByMembershipId(@Param("membershipId") UUID membershipId);

    // --- Seat limits and the platform admin console ---

    @Query("SELECT COUNT(wm) FROM WorkspaceMembership wm WHERE wm.workspace.workspaceId = :workspaceId AND wm.isActive = true")
    long countActiveMembers(@Param("workspaceId") UUID workspaceId);

    /** Rows of (workspace id, active memberships) for the given workspaces; workspaces with none are left out. */
    @Query("SELECT wm.workspace.workspaceId, COUNT(wm) FROM WorkspaceMembership wm " +
           "WHERE wm.workspace.workspaceId IN :workspaceIds AND wm.isActive = true GROUP BY wm.workspace.workspaceId")
    List<Object[]> countActiveMembersByWorkspace(@Param("workspaceIds") Collection<UUID> workspaceIds);

    @Query("SELECT COUNT(wm) FROM WorkspaceMembership wm WHERE wm.isActive = true")
    long countAllActive();

    /** Every membership of a profile (active or not) with its workspace and role, oldest first. */
    @Query("SELECT wm FROM WorkspaceMembership wm JOIN FETCH wm.workspace JOIN FETCH wm.role " +
           "WHERE wm.profile.profileId = :profileId ORDER BY wm.joinedAt ASC")
    List<WorkspaceMembership> findAllOfProfile(@Param("profileId") UUID profileId);
}
