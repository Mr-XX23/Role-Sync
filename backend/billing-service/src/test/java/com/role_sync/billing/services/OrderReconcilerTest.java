package com.role_sync.billing.services;

import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentProviderKey;
import com.role_sync.billing.models.PaymentStatus;
import com.role_sync.billing.payments.PaymentProvider;
import com.role_sync.billing.payments.PaymentProviderRegistry;
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.payments.WebhookResultKind;
import com.role_sync.billing.repository.PaymentOrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** A missed webhook must not leave a paid order pending, and polling must not hammer Stripe. */
class OrderReconcilerTest {

	private PaymentOrderRepository orders;
	private PaymentProvider stripe;
	private PaymentFulfillmentService fulfillment;
	private MutableClock clock;
	private OrderReconciler reconciler;
	private PaymentOrder order;
	private PaymentOrder settled;

	static final class MutableClock extends Clock {
		Instant now = Instant.parse("2026-09-15T00:00:00Z");

		@Override
		public ZoneOffset getZone() {
			return ZoneOffset.UTC;
		}

		@Override
		public Clock withZone(java.time.ZoneId zone) {
			return this;
		}

		@Override
		public Instant instant() {
			return now;
		}
	}

	@BeforeEach
	void setUp() {
		orders = mock(PaymentOrderRepository.class);
		stripe = mock(PaymentProvider.class);
		when(stripe.key()).thenReturn(PaymentProviderKey.STRIPE);
		when(stripe.isEnabled()).thenReturn(true);
		fulfillment = mock(PaymentFulfillmentService.class);
		clock = new MutableClock();
		reconciler = new OrderReconciler(orders, new PaymentProviderRegistry(List.of(stripe)), fulfillment, clock);

		UUID id = UUID.randomUUID();
		order = order(id, PaymentStatus.PENDING);
		settled = order(id, PaymentStatus.SUCCEEDED);
	}

	private static PaymentOrder order(UUID id, PaymentStatus status) {
		return PaymentOrder.builder()
				.id(id)
				.accountId(UUID.nameUUIDFromBytes("workspace".getBytes()))
				.userId(UUID.nameUUIDFromBytes("buyer".getBytes()))
				.packageCode("STARTER")
				.credits(1000L)
				.amountMinor(1000L)
				.currency("usd")
				.provider(PaymentProviderKey.STRIPE)
				.status(status)
				.idempotencyKey("key-1")
				.providerRef("cs_test_1")
				.build();
	}

	private WebhookOutcome paid() {
		return new WebhookOutcome("lookup:cs_test_1:paid", "checkout.session.lookup", WebhookResultKind.PAID,
				"cs_test_1", "pi_1", order.getId().toString(), 1000L, "usd", "paid");
	}

	@Test
	void settlesAPaidOrderWhoseWebhookNeverCame() {
		when(stripe.lookupCheckout(order)).thenReturn(Optional.of(paid()));
		when(fulfillment.process(PaymentProviderKey.STRIPE, paid())).thenReturn("granted 1000 credits");
		when(orders.findById(order.getId())).thenReturn(Optional.of(settled));

		assertThat(reconciler.refresh(order).getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
		verify(fulfillment).process(PaymentProviderKey.STRIPE, paid());
	}

	@Test
	void leavesAnOrderAloneWhileTheBuyerHasNotPaid() {
		when(stripe.lookupCheckout(order)).thenReturn(Optional.empty());

		assertThat(reconciler.refresh(order)).isSameAs(order);
		verify(fulfillment, never()).process(any(), any());
	}

	@Test
	void asksStripeAtMostOnceEveryFewSecondsPerOrder() {
		when(stripe.lookupCheckout(order)).thenReturn(Optional.empty());

		reconciler.refresh(order);
		clock.now = clock.now.plusSeconds(2);
		reconciler.refresh(order);
		verify(stripe, times(1)).lookupCheckout(order);

		clock.now = clock.now.plus(OrderReconciler.MIN_GAP);
		reconciler.refresh(order);
		verify(stripe, times(2)).lookupCheckout(order);
	}

	@Test
	void neverLooksUpOrdersThatAreAlreadyFinished() {
		assertThat(reconciler.refresh(settled)).isSameAs(settled);
		verify(stripe, never()).lookupCheckout(any());
	}

	@Test
	void aConcurrentSettlementIsNotAnError() {
		when(stripe.lookupCheckout(order)).thenReturn(Optional.of(paid()));
		when(fulfillment.process(PaymentProviderKey.STRIPE, paid())).thenThrow(new DataIntegrityViolationException("duplicate event"));
		when(orders.findById(order.getId())).thenReturn(Optional.of(settled));

		assertThat(reconciler.refresh(order).getStatus()).isEqualTo(PaymentStatus.SUCCEEDED);
	}

	@Test
	void theSweepLooksUpRecentPendingOrders() {
		when(orders.findTop100ByStatusAndCreatedAtAfterOrderByCreatedAtAsc(PaymentStatus.PENDING,
				clock.now.minus(OrderReconciler.SWEEP_WINDOW))).thenReturn(List.of(order));
		when(stripe.lookupCheckout(order)).thenReturn(Optional.of(paid()));
		when(fulfillment.process(PaymentProviderKey.STRIPE, paid())).thenReturn("granted 1000 credits");
		when(orders.findById(order.getId())).thenReturn(Optional.of(settled));

		reconciler.sweep();

		verify(fulfillment).process(PaymentProviderKey.STRIPE, paid());
		assertThat(Duration.ofHours(48)).isEqualTo(OrderReconciler.SWEEP_WINDOW);
	}
}
