package com.rolesync.authservice.dto.admin;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/** How many things happened on one UTC day ("2026-09-14"). */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DailyCount {

    private String date;
    private long count;
}
