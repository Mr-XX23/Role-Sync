package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.admin.PlanInput;
import com.role_sync.workspace.models.PlatformPlan;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PlanRulesTest {

    private static PlanInput input(String code, String name) {
        return PlanInput.builder().code(code).name(name).build();
    }

    private static HttpStatus statusOf(Runnable call) {
        return HttpStatus.valueOf(assertThrows(ResponseStatusException.class, call::run).getStatusCode().value());
    }

    @Test
    void validInputIsNormalized() {
        PlatformPlan plan = new PlatformPlan();
        PlanInput in = input(" pro_plus ", "  Pro Plus ");
        in.setCurrency("eur");
        in.setDescription("   ");
        PlanRules.apply(in, plan);
        assertEquals("PRO_PLUS", plan.getCode());
        assertEquals("Pro Plus", plan.getName());
        assertEquals("EUR", plan.getCurrency());
        assertNull(plan.getDescription());
        assertEquals(0, plan.getSortOrder());
    }

    @Test
    void invalidInputIsRefused() {
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> PlanRules.apply(input("1PRO", "Pro"), new PlatformPlan())));
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> PlanRules.apply(input("PRO", " "), new PlatformPlan())));
        PlanInput negative = input("PRO", "Pro");
        negative.setMaxMembers(0);
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> PlanRules.apply(negative, new PlatformPlan())));
        assertEquals(HttpStatus.BAD_REQUEST, statusOf(() -> PlanRules.apply(null, new PlatformPlan())));
    }

    @Test
    void defaultPlanCannotBeArchivedAndArchivedPlanCannotBeDefault() {
        PlatformPlan defaultPlan = PlatformPlan.builder().planId(UUID.randomUUID()).isDefault(true).build();
        assertEquals(HttpStatus.CONFLICT, statusOf(() -> PlanRules.requireArchivable(defaultPlan)));
        PlatformPlan archived = PlatformPlan.builder().planId(UUID.randomUUID()).isArchived(true).build();
        assertEquals(HttpStatus.CONFLICT, statusOf(() -> PlanRules.requireCanBeDefault(archived)));
    }

    @Test
    void archivedPlanStaysOnItsWorkspacesButIsNotNewlyAssigned() {
        PlatformPlan archived = PlatformPlan.builder().planId(UUID.randomUUID()).isArchived(true).build();
        assertDoesNotThrow(() -> PlanRules.requireAssignable(archived, archived.getPlanId()));
        assertEquals(HttpStatus.CONFLICT, statusOf(() -> PlanRules.requireAssignable(archived, null)));
    }
}
