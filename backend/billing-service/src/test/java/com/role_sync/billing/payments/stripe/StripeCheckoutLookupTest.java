package com.role_sync.billing.payments.stripe;

import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.payments.WebhookResultKind;
import com.stripe.model.checkout.Session;
import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/** How a Checkout Session fetched from Stripe's API maps onto an order. */
class StripeCheckoutLookupTest {

	private static final UUID ORDER = UUID.randomUUID();

	private static Session session(String status, String paymentStatus) {
		Session session = new Session();
		session.setId("cs_test_lookup");
		session.setStatus(status);
		session.setPaymentStatus(paymentStatus);
		session.setAmountTotal(1000L);
		session.setCurrency("usd");
		session.setPaymentIntent("pi_test_lookup");
		return session;
	}

	@Test
	void aPaidSessionSettlesTheOrderWithWhatStripeCharged() {
		Optional<WebhookOutcome> outcome = StripePaymentProvider.outcomeOf(session("complete", "paid"), ORDER);

		assertThat(outcome).isPresent();
		assertThat(outcome.get().kind()).isEqualTo(WebhookResultKind.PAID);
		assertThat(outcome.get().orderId()).isEqualTo(ORDER.toString());
		assertThat(outcome.get().amountMinor()).isEqualTo(1000L);
		assertThat(outcome.get().currency()).isEqualTo("usd");
		assertThat(outcome.get().paymentRef()).isEqualTo("pi_test_lookup");
		// Stable per session and result, so repeated look-ups are recorded once.
		assertThat(outcome.get().providerEventId()).isEqualTo("lookup:cs_test_lookup:paid");
	}

	@Test
	void anOpenOrUnpaidSessionChangesNothing() {
		assertThat(StripePaymentProvider.outcomeOf(session("open", "unpaid"), ORDER)).isEmpty();
		// Completed but still unpaid: an asynchronous method that hasn't cleared.
		assertThat(StripePaymentProvider.outcomeOf(session("complete", "unpaid"), ORDER)).isEmpty();
	}

	@Test
	void anExpiredSessionClosesTheOrder() {
		Optional<WebhookOutcome> outcome = StripePaymentProvider.outcomeOf(session("expired", "unpaid"), ORDER);

		assertThat(outcome).map(WebhookOutcome::kind).contains(WebhookResultKind.EXPIRED);
	}
}
