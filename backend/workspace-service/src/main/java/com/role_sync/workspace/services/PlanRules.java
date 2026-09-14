package com.role_sync.workspace.services;

import com.role_sync.workspace.dto.admin.PlanInput;
import com.role_sync.workspace.models.PlatformPlan;
import com.role_sync.workspace.utils.SanitizationUtils;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * The rules for platform plans, kept free of Spring and the database so they can be tested alone:
 * valid plan details, exactly one default plan, the default plan can't be archived, and archived
 * plans can't be newly assigned.
 */
public final class PlanRules {

    private static final Pattern CODE = Pattern.compile("^[A-Z][A-Z0-9_]{1,39}$");
    private static final Pattern CURRENCY = Pattern.compile("^[A-Z]{3}$");

    private PlanRules() {
    }

    /** Copies checked, normalized details from the admin's input onto the plan. */
    public static void apply(PlanInput input, PlatformPlan plan) {
        if (input == null) {
            throw badRequest("A plan needs a code and a name");
        }
        String code = input.getCode() == null ? "" : input.getCode().trim().toUpperCase(Locale.ROOT);
        if (!CODE.matcher(code).matches()) {
            throw badRequest("code must be 2-40 capital letters, digits or underscores, starting with a letter");
        }
        String name = SanitizationUtils.sanitizeText(input.getName());
        if (name == null || name.isBlank()) {
            throw badRequest("name cannot be blank");
        }
        name = name.trim();
        if (name.length() > 60) {
            throw badRequest("name can be at most 60 characters");
        }
        String description = SanitizationUtils.sanitizeText(input.getDescription());
        description = description == null || description.isBlank() ? null : description.trim();
        if (description != null && description.length() > 300) {
            throw badRequest("description can be at most 300 characters");
        }
        String currency = input.getCurrency() == null || input.getCurrency().isBlank()
                ? "USD" : input.getCurrency().trim().toUpperCase(Locale.ROOT);
        if (!CURRENCY.matcher(currency).matches()) {
            throw badRequest("currency must be a 3-letter code such as USD");
        }
        requireAtLeast("price_monthly_cents", input.getPriceMonthlyCents(), 0);
        requireAtLeast("max_members", input.getMaxMembers(), 1);
        requireAtLeast("agent_tokens_per_day", input.getAgentTokensPerDay(), 0);
        requireAtLeast("max_concurrent_agent_runs", input.getMaxConcurrentAgentRuns(), 1);
        int sortOrder = input.getSortOrder() == null ? 0 : input.getSortOrder();
        if (sortOrder < 0 || sortOrder > 10_000) {
            throw badRequest("sort_order must be between 0 and 10000");
        }

        plan.setCode(code);
        plan.setName(name);
        plan.setDescription(description);
        plan.setPriceMonthlyCents(input.getPriceMonthlyCents());
        plan.setCurrency(currency);
        plan.setMaxMembers(input.getMaxMembers());
        plan.setAgentTokensPerDay(input.getAgentTokensPerDay());
        plan.setMaxConcurrentAgentRuns(input.getMaxConcurrentAgentRuns());
        plan.setSortOrder(sortOrder);
    }

    public static void requireArchivable(PlatformPlan plan) {
        if (Boolean.TRUE.equals(plan.getIsDefault())) {
            throw conflict("The default plan can't be archived. Make another plan the default first.");
        }
    }

    public static void requireCanBeDefault(PlatformPlan plan) {
        if (Boolean.TRUE.equals(plan.getIsArchived())) {
            throw conflict("An archived plan can't be the default. Restore it first.");
        }
    }

    /** An archived plan may stay on a workspace already on it, but can't be newly assigned. */
    public static void requireAssignable(PlatformPlan plan, java.util.UUID currentPlanId) {
        if (Boolean.TRUE.equals(plan.getIsArchived()) && !plan.getPlanId().equals(currentPlanId)) {
            throw conflict("This plan is archived and can't be assigned. Restore it first.");
        }
    }

    private static void requireAtLeast(String field, Number value, long min) {
        if (value != null && value.longValue() < min) {
            throw badRequest(field + " must be at least " + min + " (or empty for no limit)");
        }
    }

    private static ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    private static ResponseStatusException conflict(String message) {
        return new ResponseStatusException(HttpStatus.CONFLICT, message);
    }
}
