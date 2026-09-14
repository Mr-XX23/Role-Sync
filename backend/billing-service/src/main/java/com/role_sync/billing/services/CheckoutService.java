package com.role_sync.billing.services;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.models.PaymentStatus;
import com.role_sync.billing.payments.CheckoutCommand;
import com.role_sync.billing.payments.PaymentProvider;
import com.role_sync.billing.payments.PaymentProviderException;
import com.role_sync.billing.payments.PaymentProviderRegistry;
import com.role_sync.billing.payments.ProviderCheckout;
import com.role_sync.billing.repository.PaymentOrderRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

/**
 * Opens a checkout for a credit package.
 *
 * <p>Deliberately not wrapped in a single transaction: it calls an external
 * gateway, and holding a database transaction open across a network round trip
 * is how connection pools get exhausted. Each step commits on its own, and the
 * order row is written before the gateway is called so a crash mid-call leaves a
 * CREATED order we can reconcile rather than a payment we have no record of.
 */
@Service
public class CheckoutService {

	private static final Logger log = LoggerFactory.getLogger(CheckoutService.class);

	private final BillingProperties properties;
	private final PaymentProviderRegistry registry;
	private final PaymentOrderRepository orders;

	public CheckoutService(BillingProperties properties,
	                       PaymentProviderRegistry registry,
	                       PaymentOrderRepository orders) {
		this.properties = properties;
		this.registry = registry;
		this.orders = orders;
	}

	/**
	 * @param idempotencyKey caller-supplied key. When absent a random one is used,
	 *                       so each call opens a fresh checkout.
	 */
	public PaymentOrder start(UUID userId,
	                          UUID accountId,
	                          String packageCode,
	                          PaymentProviderKey providerKey,
	                          String idempotencyKey) {

		BillingProperties.CreditPackage pkg = properties.findPackage(packageCode)
				.orElseThrow(() -> new IllegalArgumentException("Unknown or inactive package: " + packageCode));

		PaymentProvider provider = registry.find(providerKey)
				.filter(PaymentProvider::isEnabled)
				.orElseThrow(() -> new PaymentProviderException(
						"Payment provider " + providerKey + " is not available yet"));

		String key = resolveKey(accountId, packageCode, idempotencyKey);

		// Replaying the same key returns the checkout already in flight rather than
		// creating a second session the buyer could also pay.
		Optional<PaymentOrder> existing = orders.findByIdempotencyKey(key);
		if (existing.isPresent()) {
			PaymentOrder order = existing.get();
			if (order.getStatus() == PaymentStatus.PENDING && order.getCheckoutUrl() != null) {
				return order;
			}
			if (order.getStatus().isTerminal()) {
				throw new IllegalStateException(
						"That idempotency key was already used by a finished order; send a new key to buy again");
			}
		}

		PaymentOrder order = orders.save(PaymentOrder.builder()
				.accountId(accountId)
				.userId(userId)
				.packageCode(pkg.getCode())
				// Amount and credits are taken from configuration, never from the request,
				// so a caller cannot decide what it pays or what it receives.
				.credits(pkg.getCredits())
				.amountMinor(pkg.getPriceMinor())
				.currency(pkg.getCurrency().toLowerCase())
				.provider(providerKey)
				.status(PaymentStatus.CREATED)
				.idempotencyKey(key)
				.build());

		CheckoutCommand command = new CheckoutCommand(
				order.getId(),
				accountId,
				userId,
				pkg.getCode(),
				pkg.getName() == null ? pkg.getCode() : pkg.getName(),
				pkg.getCredits(),
				pkg.getPriceMinor(),
				order.getCurrency(),
				key,
				// The success page polls this order, so it needs to know which one it came back from.
				withOrderId(properties.getSuccessUrl(), order.getId()),
				properties.getCancelUrl());

		try {
			ProviderCheckout checkout = provider.createCheckout(command);
			order.setProviderRef(checkout.providerRef());
			order.setCheckoutUrl(checkout.checkoutUrl());
			order.setStatus(PaymentStatus.PENDING);
			return orders.save(order);
		}
		catch (RuntimeException ex) {
			order.setStatus(PaymentStatus.FAILED);
			order.setFailureReason(truncate(ex.getMessage()));
			orders.save(order);
			log.error("Checkout could not be opened for order {}: {}", order.getId(), ex.getMessage());
			throw ex;
		}
	}

	static String withOrderId(String url, UUID orderId) {
		return url + (url.contains("?") ? "&" : "?") + "orderId=" + orderId;
	}

	private String resolveKey(UUID accountId, String packageCode, String idempotencyKey) {
		if (idempotencyKey == null || idempotencyKey.isBlank()) {
			return "auto:" + UUID.randomUUID();
		}
		// Namespaced so one workspace cannot collide with, or probe, another key.
		return accountId + ":" + packageCode + ":" + idempotencyKey.trim();
	}

	private static String truncate(String value) {
		if (value == null) {
			return null;
		}
		return value.length() <= 500 ? value : value.substring(0, 500);
	}
}
