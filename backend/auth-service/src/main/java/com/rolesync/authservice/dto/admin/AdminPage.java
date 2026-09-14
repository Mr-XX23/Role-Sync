package com.rolesync.authservice.dto.admin;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.domain.Page;

import java.util.List;
import java.util.function.Function;

/** A page of a Super Admin Console list. {@code page} counts from 0. */
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

    public static <E, T> AdminPage<T> of(Page<E> page, Function<E, T> mapper) {
        return AdminPage.<T>builder()
                .items(page.getContent().stream().map(mapper).toList())
                .page(page.getNumber())
                .size(page.getSize())
                .total(page.getTotalElements())
                .totalPages(page.getTotalPages())
                .build();
    }
}
