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
 * Turns a verified webhook into an order state change and, when money settled, credits.
 *
 * <p>This is the only place an order becomes SUCCEEDED. The redirect the buyer lands on is treated
 * as cosmetic: a browser return is trivially forgeable, so fulfilment happens here, driven by a
 * signed provider callback.
 *
 * <p>It is safe to call repeatedly, which matters because every gateway retries: the event id is
 * unique, a settled order never settles again, and the ledger credits an order once.
 */
@Service
public class PaymentFulfillmentService {

	private static final Logger log = LoggerFactory.getLogger(PaymentFulfillmentService.class);

	private final PaymentOrderRepository orders;
	private final PaymentEventRepository events;
	private final CreditGrantRepository grants;
	private final CreditLedgerService ledger;

	public PaymentFulfillmentService(PaymentOrderRepository orders,
	                                 PaymentEventRepository events,
	                                 CreditGrantRepository grants,
	                                 CreditLedgerService ledger) {
		this.orders = orders;
		this.events = events;
		this.grants = grants;
		this.ledger = ledger;
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
			case ATTEMPT_FAILED -> noteFailedAttempt(order, outcome.message());
			case EXPIRED -> transitionTo(order, PaymentStatus.EXPIRED, outcome.message());
			case REFUNDED -> refund(order, outcome);
			case DISPUTED -> dispute(order, outcome);
			case IGNORED -> "ignored: " + outcome.message();
		};
	}

	private String markPaid(PaymentOrder order, WebhookOutcome outcome) {
		if (order.getStatus() == PaymentStatus.SUCCEEDED) {
			return "already settled";
		}
		if (order.getStatus() == PaymentStatus.REFUNDED) {
			log.warn("Order {} is REFUNDED but received a paid webhook; not changing it", order.getId());
			return "conflict: order already " + order.getStatus();
		}
		if (order.getStatus().isTerminal()) {
			// Money was collected after we had closed the order (events can arrive out of order).
			// The buyer paid, so they get their credits; refusing would keep money for nothing.
			log.warn("Order {} was {} but the provider reports it paid; settling it", order.getId(), order.getStatus());
		}

		// Cross-check what the gateway says was charged against what we asked for. A mismatch
		// means a tampered or misconfigured checkout, so no credits are added.
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

		boolean credited = ledger.creditPurchase(order.getAccountId(), order.getCredits(), order.getUserId(), order.getId());
		if (!grants.existsByOrderId(order.getId())) {
			grants.save(CreditGrant.builder()
					.orderId(order.getId())
					.accountId(order.getAccountId())
					.userId(order.getUserId())
					.credits(order.getCredits())
					.status(GrantStatus.APPLIED)
					.appliedAt(Instant.now())
					.build());
		}

		if (!credited) {
			return "settled; credits already added";
		}
		log.info("Order {} settled; added {} credits to workspace {}", order.getId(), order.getCredits(), order.getAccountId());
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

	/**
	 * A chargeback is the classic credit fraud: buy, spend, then dispute. Spending stops at once by
	 * suspending the workspace's credits; a super admin reactivates it once the dispute is resolved.
	 */
	private String dispute(PaymentOrder order, WebhookOutcome outcome) {
		String reason = "Payment disputed for order " + order.getId() + " (" + outcome.message() + ")";
		order.setFailureReason(reason.length() <= 500 ? reason : reason.substring(0, 500));
		orders.save(order);
		ledger.suspend(order.getAccountId(), reason, null);
		log.warn("Order {} disputed; suspended credits for workspace {}", order.getId(), order.getAccountId());
		return "disputed; workspace credits suspended";
	}

	private String noteFailedAttempt(PaymentOrder order, String reason) {
		if (order.getStatus().isTerminal()) {
			return "ignored: order already " + order.getStatus();
		}
		// Keep the order open: the same checkout can still be paid with another card.
		order.setFailureReason(reason == null ? null : reason.length() <= 500 ? reason : reason.substring(0, 500));
		orders.save(order);
		return "attempt failed; checkout still open";
	}

	private String refund(PaymentOrder order, WebhookOutcome outcome) {
		if (order.getStatus() != PaymentStatus.SUCCEEDED) {
			return "ignored: refund for a " + order.getStatus() + " order";
		}
		if (outcome.amountMinor() > 0 && outcome.amountMinor() < order.getAmountMinor()) {
			// A partial refund is a support decision about how many credits to take back, so it is
			// recorded for a super admin to settle with a deduct instead of guessed here.
			log.warn("Order {} partially refunded ({} of {} {}); credits left unchanged for manual review",
					order.getId(), outcome.amountMinor(), order.getAmountMinor(), order.getCurrency());
			order.setFailureReason("partial refund of " + outcome.amountMinor() + " " + order.getCurrency()
					+ "; review credits");
			orders.save(order);
			return "partial refund recorded; credits unchanged";
		}
		order.setStatus(PaymentStatus.REFUNDED);
		orders.save(order);
		boolean clawed = ledger.clawBackPurchase(order.getAccountId(), order.getCredits(), order.getId());
		log.warn("Order {} refunded; removed {} credits from workspace {}", order.getId(), order.getCredits(), order.getAccountId());
		return clawed ? "refunded; credits removed" : "refunded; credits already removed";
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
