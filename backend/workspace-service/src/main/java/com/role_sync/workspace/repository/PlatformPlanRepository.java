package com.role_sync.workspace.repository;

import com.role_sync.workspace.models.PlatformPlan;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface PlatformPlanRepository extends JpaRepository<PlatformPlan, UUID> {

    /**
     * Every plan, locked until the surrounding transaction ends. Plan changes take this lock first,
     * so they run one at a time and the one-default / default-not-archived rules can't be raced.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT p FROM PlatformPlan p ORDER BY p.sortOrder ASC, p.name ASC")
    List<PlatformPlan> lockAll();

    @Query("SELECT p FROM PlatformPlan p WHERE p.isDefault = true ORDER BY p.sortOrder ASC, p.name ASC")
    List<PlatformPlan> findDefaults();
}
