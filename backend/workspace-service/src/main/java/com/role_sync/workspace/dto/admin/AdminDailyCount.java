package com.role_sync.workspace.dto.admin;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;

/** How many things happened on one UTC day. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminDailyCount {

    private LocalDate date;

    private long count;
}
