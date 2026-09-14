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
import com.role_sync.billing.payments.WebhookOutcome;
import com.role_sync.billing.repository.PaymentOrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CheckoutServiceTest {

	/** Records what the gateway was asked to charge. */
	private static final class RecordingProvider implements PaymentProvider {
		private CheckoutCommand received;
		private boolean enabled = true;

		@Override
		public PaymentProviderKey key() {
			return PaymentProviderKey.STRIPE;
		}

		@Override
		public boolean isEnabled() {
			return enabled;
		}

		@Override
		public ProviderCheckout createCheckout(CheckoutCommand command) {
			this.received = command;
			return new ProviderCheckout("cs_test_123", "https://checkout.stripe.test/cs_test_123");
		}

		@Override
		public WebhookOutcome parseWebhook(String rawBody, String signatureHeader) {
			throw new UnsupportedOperationException();
		}
	}

	private BillingProperties properties;
	private PaymentOrderRepository orders;
	private RecordingProvider provider;
	private CheckoutService service;

	@BeforeEach
	void setUp() {
		properties = new BillingProperties();
		BillingProperties.CreditPackage starter = new BillingProperties.CreditPackage();
		starter.setCode("STARTER");
		starter.setName("Starter");
		starter.setCredits(1000L);
		starter.setPriceMinor(1000L);
		starter.setCurrency("usd");
		properties.setPackages(List.of(starter));

		orders = mock(PaymentOrderRepository.class);
		when(orders.save(any(PaymentOrder.class))).thenAnswer(i -> {
			PaymentOrder o = i.getArgument(0);
			if (o.getId() == null) {
				o.setId(UUID.randomUUID());
			}
			return o;
		});
		when(orders.findByIdempotencyKey(any())).thenReturn(Optional.empty());

		provider = new RecordingProvider();
		service = new CheckoutService(properties, new PaymentProviderRegistry(List.of(provider)), orders);
	}

	@Test
	void chargesTheConfiguredPriceNotAnythingFromTheCaller() {
		PaymentOrder order = service.start(UUID.randomUUID(), UUID.randomUUID(),
				"STARTER", PaymentProviderKey.STRIPE, "idem-1");

		// The price the gateway is told to collect must come from configuration.
		assertThat(provider.received.amountMinor()).isEqualTo(1000L);
		assertThat(provider.received.credits()).isEqualTo(1000L);
		assertThat(order.getAmountMinor()).isEqualTo(1000L);
		assertThat(order.getCredits()).isEqualTo(1000L);
		assertThat(order.getStatus()).isEqualTo(PaymentStatus.PENDING);
		assertThat(order.getCheckoutUrl()).isEqualTo("https://checkout.stripe.test/cs_test_123");
		assertThat(order.getProviderRef()).isEqualTo("cs_test_123");
	}

	@Test
	void rejectsAnUnknownPackage() {
		assertThatThrownBy(() -> service.start(UUID.randomUUID(), UUID.randomUUID(),
				"DOES_NOT_EXIST", PaymentProviderKey.STRIPE, null))
				.isInstanceOf(IllegalArgumentException.class)
				.hasMessageContaining("Unknown or inactive package");
	}

	@Test
	void rejectsAProviderThatIsNotWiredYet() {
		assertThatThrownBy(() -> service.start(UUID.randomUUID(), UUID.randomUUID(),
				"STARTER", PaymentProviderKey.ESEWA, null))
				.isInstanceOf(PaymentProviderException.class)
				.hasMessageContaining("ESEWA");
	}

	@Test
	void namespacesTheIdempotencyKeyByWorkspace() {
		UUID workspace = UUID.randomUUID();
		service.start(UUID.randomUUID(), workspace, "STARTER", PaymentProviderKey.STRIPE, "shared-key");

		assertThat(provider.received.idempotencyKey()).startsWith(workspace.toString());
	}
}
