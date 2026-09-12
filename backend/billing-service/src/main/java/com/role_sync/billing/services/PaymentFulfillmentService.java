package com.role_sync.billing.services;

import com.role_sync.billing.models.CreditGrant;
import com.role_sync.billing.models.GrantStatus;
import com.role_sync.billing.models.PaymentEvent;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.models.PaymentStatus;
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.repository.CreditGrantRepository;
import com.role_sync.billing.repository.PaymentEventRepository;
import com.role_sync.billing.repository.PaymentOrderRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/**
 * Turns a verified webhook into an order state change and, when money settled, a
 * credit grant.
 *
 * <p>This is the only place an order becomes SUCCEEDED. The redirect the buyer
 * lands on is treated as cosmetic: a browser return is trivially forgeable, so
 * fulfilment happens here, driven by a signed provider callback.
 *
 * <p>Three things make it safe to call repeatedly, which matters because every
 * gateway retries: the event id is unique, only a non-terminal order transitions,
 * and the grant is unique per order.
 */
@Service
public class PaymentFulfillmentService {

	private static final Logger log = LoggerFactory.getLogger(PaymentFulfillmentService.class);

	private final PaymentOrderRepository orders;
	private final PaymentEventRepository events;
	private final CreditGrantRepository grants;

	public PaymentFulfillmentService(PaymentOrderRepository orders,
	                                 PaymentEventRepository events,
	                                 CreditGrantRepository grants) {
		this.orders = orders;
		this.events = events;
		this.grants = grants;
	}

	@Transactional
	public String process(PaymentProviderKey provider, WebhookOutcome outcome) {
		if (events.existsByProviderAndProviderEventId(provider, outcome.providerEventId())) {
			log.info("Ignoring duplicate {} webhook {}", provider, outcome.providerEventId());
			return "duplicate";
		}

		Optional<PaymentOrder> found = resolveOrder(outcome);
		String result;

		if (found.isEmpty()) {
			result = "no matching order";
			log.warn("{} webhook {} ({}) matched no order", provider, outcome.providerEventId(), outcome.eventType());
		}
		else {
			result = apply(found.get(), outcome);
		}

		events.save(PaymentEvent.builder()
				.provider(provider)
				.providerEventId(outcome.providerEventId())
				.eventType(outcome.eventType())
				.orderId(found.map(PaymentOrder::getId).orElse(null))
				.signatureVerified(true)
				.outcome(result)
				.build());

		return result;
	}

	private String apply(PaymentOrder order, WebhookOutcome outcome) {
		return switch (outcome.kind()) {
			case PAID -> markPaid(order, outcome);
			case FAILED -> transitionTo(order, PaymentStatus.FAILED, outcome.message());
			case EXPIRED -> transitionTo(order, PaymentStatus.EXPIRED, outcome.message());
			case REFUNDED -> refund(order);
			case IGNORED -> "ignored: " + outcome.message();
		};
	}

	private String markPaid(PaymentOrder order, WebhookOutcome outcome) {
		if (order.getStatus() == PaymentStatus.SUCCEEDED) {
			return "already settled";
		}
		if (order.getStatus().isTerminal()) {
			log.warn("Order {} is {} but received a paid webhook; not changing it",
					order.getId(), order.getStatus());
			return "conflict: order already " + order.getStatus();
		}

		// Cross-check what the gateway says was charged against what we asked for.
		// A mismatch means a tampered or misconfigured checkout, so we refuse to
		// grant credits and leave it for a human.
		if (outcome.amountMinor() > 0 && outcome.amountMinor() != order.getAmountMinor()) {
			log.error("Amount mismatch on order {}: expected {} {}, provider reported {} {}",
					order.getId(), order.getAmountMinor(), order.getCurrency(),
					outcome.amountMinor(), outcome.currency());
			order.setFailureReason("amount mismatch: expected " + order.getAmountMinor()
					+ ", provider reported " + outcome.amountMinor());
			orders.save(order);
			return "rejected: amount mismatch";
		}
		if (outcome.currency() != null && !outcome.currency().equalsIgnoreCase(order.getCurrency())) {
			log.error("Currency mismatch on order {}: expected {}, provider reported {}",
					order.getId(), order.getCurrency(), outcome.currency());
			order.setFailureReason("currency mismatch: expected " + order.getCurrency()
					+ ", provider reported " + outcome.currency());
			orders.save(order);
			return "rejected: currency mismatch";
		}

		order.setStatus(PaymentStatus.SUCCEEDED);
		order.setPaidAt(Instant.now());
		if (outcome.paymentRef() != null) {
			order.setProviderPaymentRef(outcome.paymentRef());
		}
		order.setFailureReason(null);
		orders.save(order);

		// The grant is the handover to the credit domain. Unique per order, so a
		// replayed webhook cannot grant twice.
		if (grants.existsByOrderId(order.getId())) {
			return "settled; grant already present";
		}
		grants.save(CreditGrant.builder()
				.orderId(order.getId())
				.accountId(order.getAccountId())
				.userId(order.getUserId())
				.credits(order.getCredits())
				.status(GrantStatus.PENDING)
				.build());

		log.info("Order {} settled; queued grant of {} credits to account {}",
				order.getId(), order.getCredits(), order.getAccountId());
		return "granted " + order.getCredits() + " credits";
	}

	private String transitionTo(PaymentOrder order, PaymentStatus status, String reason) {
		if (order.getStatus().isTerminal()) {
			return "ignored: order already " + order.getStatus();
		}
		order.setStatus(status);
		order.setFailureReason(reason);
		orders.save(order);
		return status.name().toLowerCase();
	}

	private String refund(PaymentOrder order) {
		if (order.getStatus() != PaymentStatus.SUCCEEDED) {
			return "ignored: refund for a " + order.getStatus() + " order";
		}
		order.setStatus(PaymentStatus.REFUNDED);
		orders.save(order);
		// Reclaiming already-spent credits is a ledger decision, not a payment one,
		// so it is deliberately left to the credit system.
		log.warn("Order {} refunded; credit clawback for account {} is pending the credit ledger",
				order.getId(), order.getAccountId());
		return "refunded";
	}

	private Optional<PaymentOrder> resolveOrder(WebhookOutcome outcome) {
		if (outcome.orderId() != null) {
			try {
				Optional<PaymentOrder> byId = orders.findById(UUID.fromString(outcome.orderId()));
				if (byId.isPresent()) {
					return byId;
				}
			}
			catch (IllegalArgumentException ignored) {
				// Metadata was not a UUID; fall through to the provider references.
			}
		}
		if (outcome.providerRef() != null) {
			Optional<PaymentOrder> byRef = orders.findByProviderRef(outcome.providerRef());
			if (byRef.isPresent()) {
				return byRef;
			}
		}
		if (outcome.paymentRef() != null) {
			return orders.findByProviderPaymentRef(outcome.paymentRef());
		}
		return Optional.empty();
	}
}
