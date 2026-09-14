package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** Ticket counts for the admin console's support queue. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminSupportTicketStats {

    private long total;

    private long open;

    @JsonProperty("in_progress")
    private long inProgress;

    private long resolved;

    private long closed;

    /** Open or in-progress tickets where the reporter wrote last: the team owes an answer. */
    @JsonProperty("awaiting_support")
    private long awaitingSupport;

    @JsonProperty("opened_last_7_days")
    private long openedLast7Days;
}
