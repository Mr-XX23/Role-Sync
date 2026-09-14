package com.role_sync.workspace.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/** One page of an admin list. {@code page} counts from 0. */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminPage<T> {

    private List<T> items;

    private int page;

    private int size;

    private long total;

    @JsonProperty("total_pages")
    private int totalPages;

    public static <T> AdminPage<T> of(List<T> items, int page, int size, long total) {
        int totalPages = size <= 0 ? 0 : (int) Math.min(Integer.MAX_VALUE, (total + size - 1) / size);
        return new AdminPage<>(items, page, size, total, totalPages);
    }
}
