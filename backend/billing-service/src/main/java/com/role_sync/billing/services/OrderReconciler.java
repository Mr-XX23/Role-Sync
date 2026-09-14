package com.role_sync.billing.services;

import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentStatus;
import com.role_sync.billing.payments.PaymentProvider;
import com.role_sync.billing.payments.PaymentProviderRegistry;
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.repository.PaymentOrderRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Settles orders whose webhook hasn't arrived by asking the payment provider directly.
 *
 * <p>The webhook stays the normal path. This covers the gaps: a stack the provider cannot reach
 * (local development without {@code stripe listen}), a delivery that failed, or an endpoint that
 * was misconfigured. The success page's polling triggers a look-up, and a sweep catches buyers who
 * closed the page. Both go through {@link PaymentFulfillmentService}, so an order is still credited
 * once, however many of the webhook, the page and the sweep see it paid.
 */
@Service
public class OrderReconciler {

	private static final Logger log = LoggerFactory.getLogger(OrderReconciler.class);

	/** How often one order may be looked up; the success page polls every two seconds. */
	static final Duration MIN_GAP = Duration.ofSeconds(5);
	/** Checkout sessions expire after a day, so older pending orders have nothing left to settle. */
	static final Duration SWEEP_WINDOW = Duration.ofHours(48);

	private final PaymentOrderRepository orders;
	private final PaymentProviderRegistry registry;
	private final PaymentFulfillmentService fulfillment;
	private final Clock clock;
	private final Map<UUID, Instant> lastLookup = new ConcurrentHashMap<>();

	@Autowired
	public OrderReconciler(PaymentOrderRepository orders, PaymentProviderRegistry registry, PaymentFulfillmentService fulfillment) {
		this(orders, registry, fulfillment, Clock.systemUTC());
	}

	OrderReconciler(PaymentOrderRepository orders, PaymentProviderRegistry registry, PaymentFulfillmentService fulfillment, Clock clock) {
		this.orders = orders;
		this.registry = registry;
		this.fulfillment = fulfillment;
		this.clock = clock;
	}

	/**
	 * Brings a pending order up to date with the provider, if its last look-up wasn't moments ago.
	 * Never throws for provider or race trouble: the caller gets the order as it now stands.
	 */
	public PaymentOrder refresh(PaymentOrder order) {
		if (order.getStatus() != PaymentStatus.PENDING || order.getProviderRef() == null) {
			return order;
		}
		Instant now = clock.instant();
		Instant previous = lastLookup.get(order.getId());
		if (previous != null && Duration.between(previous, now).compareTo(MIN_GAP) < 0) {
			return order;
		}
		lastLookup.put(order.getId(), now);

		Optional<WebhookOutcome> outcome = registry.find(order.getProvider())
				.filter(PaymentProvider::isEnabled)
				.flatMap(provider -> provider.lookupCheckout(order));
		if (outcome.isEmpty()) {
			return order;
		}
		try {
			String result = fulfillment.process(order.getProvider(), outcome.get());
			log.info("Order {} reconciled with {} without a webhook: {}", order.getId(), order.getProvider(), result);
		}
		catch (DataIntegrityViolationException | ObjectOptimisticLockingFailureException raced) {
			// The webhook, another poll or the sweep settled it at the same moment; theirs stands.
			log.debug("Order {} was settled concurrently", order.getId());
		}
		lastLookup.remove(order.getId());
		return orders.findById(order.getId()).orElse(order);
	}

	/** Every minute: look up pending orders from the last two days, so closing the page loses nothing. */
	@Scheduled(fixedDelayString = "${billing.reconcile.interval-ms:60000}", initialDelayString = "${billing.reconcile.initial-delay-ms:30000}")
	public void sweep() {
		List<PaymentOrder> pending = orders.findTop100ByStatusAndCreatedAtAfterOrderByCreatedAtAsc(
				PaymentStatus.PENDING, clock.instant().minus(SWEEP_WINDOW));
		for (PaymentOrder order : pending) {
			try {
				refresh(order);
			}
			catch (RuntimeException ex) {
				log.warn("Could not reconcile order {}: {}", order.getId(), ex.getMessage());
			}
		}
		if (lastLookup.size() > 10_000) {
			lastLookup.clear();
		}
	}
}
