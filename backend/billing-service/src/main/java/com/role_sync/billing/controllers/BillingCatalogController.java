package com.role_sync.billing.controllers;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.dto.CreditPackageResponse;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.payments.PaymentProviderRegistry;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

/** What a buyer can purchase, and which gateways are live. */
@RestController
@RequestMapping("/api/v1/billing")
public class BillingCatalogController {

	private final BillingProperties properties;
	private final PaymentProviderRegistry registry;

	public BillingCatalogController(BillingProperties properties, PaymentProviderRegistry registry) {
		this.properties = properties;
		this.registry = registry;
	}

	@GetMapping("/packages")
	public ResponseEntity<Map<String, Object>> packages() {
		List<CreditPackageResponse> active = properties.getPackages().stream()
				.filter(BillingProperties.CreditPackage::isActive)
				.sorted(Comparator.comparingInt(BillingProperties.CreditPackage::getSort))
				.map(CreditPackageResponse::from)
				.toList();

		List<PaymentProviderKey> providers = registry.enabledKeys();

		return ResponseEntity.ok(Map.of(
				"packages", active,
				"providers", providers));
	}

	@GetMapping("/health")
	public ResponseEntity<Map<String, Object>> health() {
		return ResponseEntity.ok(Map.of(
				"status", "UP",
				"service", "billing-service",
				"providers", registry.enabledKeys()));
	}
}
