package com.role_sync.workspace.configurations;

import com.role_sync.workspace.models.PlatformPlan;
import com.role_sync.workspace.repository.PlatformPlanRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Component;

/**
 * A workspace with no plan is on the default plan, so there must be one. When the platform has
 * no plans at all, creates a "Standard" default plan with no limits of its own (platform defaults
 * apply). Idempotent; a concurrent instance creating it first is fine (unique code).
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class DefaultPlanSeeder implements ApplicationRunner {

    private final PlatformPlanRepository plans;

    @Override
    public void run(ApplicationArguments args) {
        try {
            if (plans.count() > 0) {
                return;
            }
            plans.saveAndFlush(PlatformPlan.builder()
                    .code("STANDARD")
                    .name("Standard")
                    .description("The plan every workspace is on unless the RoleSync team assigns another.")
                    .isDefault(true)
                    .build());
            log.info("Seeded the default platform plan STANDARD");
        } catch (DataIntegrityViolationException e) {
            log.info("Default platform plan was seeded by another instance");
        } catch (RuntimeException e) {
            log.warn("Could not seed the default platform plan: {}", e.getMessage());
        }
    }
}
