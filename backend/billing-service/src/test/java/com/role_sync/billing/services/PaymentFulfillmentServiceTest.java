package com.role_sync.billing.services;

import com.role_sync.billing.models.CreditGrant;
import com.role_sync.billing.models.PaymentEvent;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.models.PaymentStatus;
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.payments.WebhookResultKind;
import com.role_sync.billing.repository.CreditGrantRepository;
import com.role_sync.billing.repository.PaymentEventRepository;
import com.role_sync.billing.repository.PaymentOrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Fulfilment is the only place money becomes credits, so these cover the ways it
 * could pay out twice or pay out the wrong amount.
 */
class PaymentFulfillmentServiceTest {

	private PaymentOrderRepository orders;
	private PaymentEventRepository events;
	private CreditGrantRepository grants;
	private CreditLedgerService ledger;
	private PaymentFulfillmentService service;

	private PaymentOrder order;

	@BeforeEach
	void setUp() {
		orders = mock(PaymentOrderRepository.class);
		events = mock(PaymentEventRepository.class);
		grants = mock(CreditGrantRepository.class);
		ledger = mock(CreditLedgerService.class);
		when(ledger.creditPurchase(any(), anyLong(), any(), any())).thenReturn(true);
		when(ledger.clawBackPurchase(any(), anyLong(), any())).thenReturn(true);
		service = new PaymentFulfillmentService(orders, events, grants, ledger);

		order = PaymentOrder.builder()
				.id(UUID.randomUUID())
				.accountId(UUID.randomUUID())
				.userId(UUID.randomUUID())
				.packageCode("STARTER")
				.credits(1000L)
				.amountMinor(1000L)
				.currency("usd")
				.provider(PaymentProviderKey.STRIPE)
				.status(PaymentStatus.PENDING)
				.idempotencyKey("key-1")
				.providerRef("cs_test_1")
				.build();

		when(orders.save(any(PaymentOrder.class))).thenAnswer(i -> i.getArgument(0));
		when(events.save(any(PaymentEvent.class))).thenAnswer(i -> i.getArgument(0));
		when(grants.save(any(CreditGrant.class))).thenAnswer(i -> i.getArgument(0));
	}

	private WebhookOutcome paid(String eventId, long amountMinor, String currency) {
		return new WebhookOutcome(eventId, "checkout.session.completed", WebhookResultKind.PAID,
				"cs_test_1", "pi_test_1", order.getId().toString(), amountMinor, currency, "paid");
	}

	@Test
	void grantsCreditsOnceWhenPaymentSettles() {
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));
		when(grants.existsByOrderId(order.getId())).thenReturn(false);

		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_1", 1000L, "usd"));

		assertThat(result).contains("granted 1000 credits");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
		assertThat(order.getPaidAt()).isNotNull();
		assertThat(order.getProviderPaymentRef()).isEqualTo("pi_test_1");
		verify(grants).save(any(CreditGrant.class));
		verify(ledger).creditPurchase(order.getAccountId(), 1000L, order.getUserId(), order.getId());
	}

	@Test
	void ignoresAReplayedEventWithoutGrantingAgain() {
		// Stripe retries until it gets a 2xx, so the same event id will arrive twice.
		when(events.existsByProviderAndProviderEventId(eq(PaymentProviderKey.STRIPE), eq("evt_1")))
				.thenReturn(true);

		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_1", 1000L, "usd"));

		assertThat(result).isEqualTo("duplicate");
		verify(grants, never()).save(any(CreditGrant.class));
		verify(ledger, never()).creditPurchase(any(), anyLong(), any(), any());
		verify(orders, never()).save(any(PaymentOrder.class));
	}

	@Test
	void doesNotGrantTwiceWhenTheOrderIsAlreadySettled() {
		order.setStatus(PaymentStatus.SUCCEEDED);
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_2", 1000L, "usd"));

		assertThat(result).isEqualTo("already settled");
		verify(grants, never()).save(any(CreditGrant.class));
		verify(ledger, never()).creditPurchase(any(), anyLong(), any(), any());
	}

	@Test
	void refusesToGrantWhenTheProviderReportsADifferentAmount() {
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		// Provider says 1 cent was paid for a 1000-cent package.
		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_3", 1L, "usd"));

		assertThat(result).isEqualTo("rejected: amount mismatch");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.PENDING);
		verify(grants, never()).save(any(CreditGrant.class));
		verify(ledger, never()).creditPurchase(any(), anyLong(), any(), any());
	}

	@Test
	void refusesToGrantWhenTheCurrencyDoesNotMatch() {
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_4", 1000L, "npr"));

		assertThat(result).isEqualTo("rejected: currency mismatch");
		verify(grants, never()).save(any(CreditGrant.class));
		verify(ledger, never()).creditPurchase(any(), anyLong(), any(), any());
	}

	@Test
	void recordsAnAuditRowEvenWhenNoOrderMatches() {
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(any(UUID.class))).thenReturn(Optional.empty());
		when(orders.findByProviderRef(any())).thenReturn(Optional.empty());
		when(orders.findByProviderPaymentRef(any())).thenReturn(Optional.empty());

		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_5", 1000L, "usd"));

		assertThat(result).isEqualTo("no matching order");
		verify(events).save(any(PaymentEvent.class));
		verify(grants, never()).save(any(CreditGrant.class));
		verify(ledger, never()).creditPurchase(any(), anyLong(), any(), any());
	}

	@Test
	void expiredCheckoutClosesTheOrderWithoutGranting() {
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		WebhookOutcome outcome = new WebhookOutcome("evt_6", "checkout.session.expired",
				WebhookResultKind.EXPIRED, "cs_test_1", null, order.getId().toString(),
				0L, "usd", "expired");

		String result = service.process(PaymentProviderKey.STRIPE, outcome);

		assertThat(result).isEqualTo("expired");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.EXPIRED);
		verify(grants, never()).save(any(CreditGrant.class));
		verify(ledger, never()).creditPurchase(any(), anyLong(), any(), any());
	}

	@Test
	void aDeclinedCardKeepsTheCheckoutOpenSoARetryCanStillPay() {
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		WebhookOutcome declined = new WebhookOutcome("evt_8", "payment_intent.payment_failed",
				WebhookResultKind.ATTEMPT_FAILED, null, "pi_test_1", order.getId().toString(), 1000L, "usd",
				"payment failed: Your card was declined.");

		assertThat(service.process(PaymentProviderKey.STRIPE, declined)).isEqualTo("attempt failed; checkout still open");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.PENDING);

		// The buyer tries another card in the same session.
		assertThat(service.process(PaymentProviderKey.STRIPE, paid("evt_9", 1000L, "usd"))).contains("granted 1000 credits");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
		assertThat(order.getFailureReason()).isNull();
	}

	@Test
	void aPaymentThatSettlesAfterTheOrderWasClosedStillAddsCredits() {
		order.setStatus(PaymentStatus.EXPIRED);
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		String result = service.process(PaymentProviderKey.STRIPE, paid("evt_10", 1000L, "usd"));

		assertThat(result).contains("granted 1000 credits");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
		verify(ledger).creditPurchase(order.getAccountId(), 1000L, order.getUserId(), order.getId());
	}

	@Test
	void refundTakesThePurchasedCreditsBack() {
		order.setStatus(PaymentStatus.SUCCEEDED);
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		WebhookOutcome outcome = new WebhookOutcome("evt_7", "charge.refunded", WebhookResultKind.REFUNDED,
				null, "pi_test_1", order.getId().toString(), 1000L, "usd", "refunded");

		String result = service.process(PaymentProviderKey.STRIPE, outcome);

		assertThat(result).isEqualTo("refunded; credits removed");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.REFUNDED);
		verify(ledger).clawBackPurchase(order.getAccountId(), 1000L, order.getId());
	}

	@Test
	void aChargebackSuspendsTheWorkspacesCredits() {
		order.setStatus(PaymentStatus.SUCCEEDED);
		order.setProviderPaymentRef("pi_test_1");
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findByProviderPaymentRef("pi_test_1")).thenReturn(Optional.of(order));

		WebhookOutcome outcome = new WebhookOutcome("evt_12", "charge.dispute.created", WebhookResultKind.DISPUTED,
				null, "pi_test_1", null, 1000L, "usd", "payment disputed: fraudulent");

		assertThat(service.process(PaymentProviderKey.STRIPE, outcome)).isEqualTo("disputed; workspace credits suspended");
		verify(ledger).suspend(eq(order.getAccountId()), any(), eq(null));
	}

	@Test
	void aPartialRefundLeavesCreditsForAnAdminToSettle() {
		order.setStatus(PaymentStatus.SUCCEEDED);
		when(events.existsByProviderAndProviderEventId(any(), any())).thenReturn(false);
		when(orders.findById(order.getId())).thenReturn(Optional.of(order));

		WebhookOutcome outcome = new WebhookOutcome("evt_11", "charge.refunded", WebhookResultKind.REFUNDED,
				null, "pi_test_1", order.getId().toString(), 400L, "usd", "refunded");

		assertThat(service.process(PaymentProviderKey.STRIPE, outcome)).isEqualTo("partial refund recorded; credits unchanged");
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
		verify(ledger, never()).clawBackPurchase(any(), anyLong(), any());
	}
}
