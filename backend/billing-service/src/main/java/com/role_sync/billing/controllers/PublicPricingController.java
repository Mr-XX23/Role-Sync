package com.role_sync.billing.controllers;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.dto.CreditDtos.PricingExample;
import com.role_sync.billing.dto.CreditDtos.PublicPricingResponse;
import com.role_sync.billing.dto.CreditPackageResponse;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;
import java.util.Comparator;
import java.util.List;

/** Prices for the public pricing page. No sign-in; the gateway lists this path as public. */
@RestController
@RequestMapping("/api/v1/billing/public")
public class PublicPricingController {

	private final BillingProperties properties;

	public PublicPricingController(BillingProperties properties) {
		this.properties = properties;
	}

	@GetMapping("/pricing")
	public ResponseEntity<PublicPricingResponse> pricing() {
		List<CreditPackageResponse> packages = properties.getPackages().stream()
				.filter(BillingProperties.CreditPackage::isActive)
				.sorted(Comparator.comparingInt(BillingProperties.CreditPackage::getSort))
				.map(CreditPackageResponse::from)
				.toList();
		String currency = packages.isEmpty() ? "usd" : packages.get(0).currency();
		List<PricingExample> examples = properties.getExamples().stream()
				.map(example -> new PricingExample(example.getLabel(), example.getCredits()))
				.toList();

		return ResponseEntity.ok()
				.cacheControl(CacheControl.maxAge(Duration.ofMinutes(5)).cachePublic())
				.body(new PublicPricingResponse(
						currency,
						properties.getCredits().getSignupGrant(),
						properties.getCredits().getPriceUsd(),
						packages,
						examples));
	}
}
