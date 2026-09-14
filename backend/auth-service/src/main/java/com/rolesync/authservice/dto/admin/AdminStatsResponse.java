package com.rolesync.authservice.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/** Sign-in account numbers for the Super Admin Console overview. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminStatsResponse {

    @JsonProperty("total_users")
    private long totalUsers;

    private long active;

    private long inactive;

    private long suspended;

    private long locked;

    @JsonProperty("email_verified")
    private long emailVerified;

    @JsonProperty("new_last_7_days")
    private long newLast7Days;

    @JsonProperty("new_last_30_days")
    private long newLast30Days;

    /** Accounts per login type; types nobody uses are left out. */
    @JsonProperty("login_types")
    private Map<String, Long> loginTypes;

    /** The configured allowlist (an address on it is only a super admin once verified and active). */
    @JsonProperty("super_admin_emails")
    private List<String> superAdminEmails;

    /** One entry per UTC day of the range, oldest first. */
    @JsonProperty("signups_daily")
    private List<DailyCount> signupsDaily;

    /** Successful password and Google sign-ins, one entry per UTC day of the range, oldest first. */
    @JsonProperty("sign_ins_daily")
    private List<DailyCount> signInsDaily;
}
