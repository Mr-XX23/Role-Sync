package com.rolesync.authservice.configurations;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Wraps Spring Security's default resolver so every authorization request sent
 * to the identity provider carries {@code prompt=select_account}.
 *
 * Without it Google reuses whichever account is already signed in to the
 * browser and never shows the account chooser, so a user who logs out of
 * RoleSync and clicks "Google" again is silently signed back in to the same
 * account and cannot pick a different one.
 */
public class OAuth2AccountChooserRequestResolver implements OAuth2AuthorizationRequestResolver {

        static final String PROMPT_PARAM = "prompt";
        static final String SELECT_ACCOUNT = "select_account";

        private final OAuth2AuthorizationRequestResolver delegate;

        public OAuth2AccountChooserRequestResolver(ClientRegistrationRepository clientRegistrationRepository,
                        String authorizationRequestBaseUri) {
                this(new DefaultOAuth2AuthorizationRequestResolver(clientRegistrationRepository,
                                authorizationRequestBaseUri));
        }

        OAuth2AccountChooserRequestResolver(OAuth2AuthorizationRequestResolver delegate) {
                this.delegate = delegate;
        }

        @Override
        public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
                return withAccountChooser(delegate.resolve(request));
        }

        @Override
        public OAuth2AuthorizationRequest resolve(HttpServletRequest request, String clientRegistrationId) {
                return withAccountChooser(delegate.resolve(request, clientRegistrationId));
        }

        private static OAuth2AuthorizationRequest withAccountChooser(OAuth2AuthorizationRequest original) {
                if (original == null) {
                        return null;
                }
                Map<String, Object> extra = new LinkedHashMap<>(original.getAdditionalParameters());
                extra.put(PROMPT_PARAM, SELECT_ACCOUNT);
                return OAuth2AuthorizationRequest.from(original)
                                .additionalParameters(extra)
                                .build();
        }
}
