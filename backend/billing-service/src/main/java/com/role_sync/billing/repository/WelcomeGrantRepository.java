package com.role_sync.billing.repository;

import com.role_sync.billing.models.WelcomeGrant;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface WelcomeGrantRepository extends JpaRepository<WelcomeGrant, UUID> {
}
