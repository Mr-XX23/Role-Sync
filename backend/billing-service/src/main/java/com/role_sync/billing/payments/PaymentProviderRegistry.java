package com.role_sync.billing.payments;

import com.role_sync.billing.models.PaymentProviderKey;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Resolves a gateway by key. Spring injects every {@link PaymentProvider} bean,
 * so registering eSewa or Khalti later is just adding a component.
 */
@Component
public class PaymentProviderRegistry {

	private final Map<PaymentProviderKey, PaymentProvider> providers = new EnumMap<>(PaymentProviderKey.class);

	public PaymentProviderRegistry(List<PaymentProvider> discovered) {
		for (PaymentProvider provider : discovered) {
			providers.put(provider.key(), provider);
		}
	}

	public Optional<PaymentProvider> find(PaymentProviderKey key) {
		return Optional.ofNullable(providers.get(key));
	}

	/** Providers that are both registered and configured. */
	public List<PaymentProviderKey> enabledKeys() {
		return providers.values().stream()
				.filter(PaymentProvider::isEnabled)
				.map(PaymentProvider::key)
				.sorted()
				.toList();
	}
}
