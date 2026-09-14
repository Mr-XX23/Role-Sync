package com.rolesync.authservice.configurations;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class OAuth2AccountChooserRequestResolverTest {

        private static OAuth2AuthorizationRequest googleRequest(Map<String, Object> additional) {
                return OAuth2AuthorizationRequest.authorizationCode()
                                .authorizationUri("https://accounts.google.com/o/oauth2/v2/auth")
                                .clientId("client-id")
                                .redirectUri("http://localhost:8080/api/v1/auth/oauth2/callback/google")
                                .state("state")
                                .additionalParameters(additional)
                                .build();
        }

        @Test
        void addsSelectAccountPromptToResolvedRequest() {
                OAuth2AuthorizationRequestResolver delegate = mock(OAuth2AuthorizationRequestResolver.class);
                HttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/auth/oauth2/authorization/google");
                when(delegate.resolve(any(HttpServletRequest.class))).thenReturn(googleRequest(Map.of()));
                when(delegate.resolve(any(HttpServletRequest.class), eq("google"))).thenReturn(googleRequest(Map.of()));

                OAuth2AccountChooserRequestResolver resolver = new OAuth2AccountChooserRequestResolver(delegate);

                OAuth2AuthorizationRequest resolved = resolver.resolve(request);
                assertThat(resolved.getAdditionalParameters()).containsEntry("prompt", "select_account");
                assertThat(resolved.getAuthorizationRequestUri()).contains("prompt=select_account");

                OAuth2AuthorizationRequest byId = resolver.resolve(request, "google");
                assertThat(byId.getAdditionalParameters()).containsEntry("prompt", "select_account");
        }

        @Test
        void keepsExistingAdditionalParameters() {
                OAuth2AuthorizationRequestResolver delegate = mock(OAuth2AuthorizationRequestResolver.class);
                when(delegate.resolve(any(HttpServletRequest.class)))
                                .thenReturn(googleRequest(Map.of("access_type", "offline")));

                OAuth2AuthorizationRequest resolved = new OAuth2AccountChooserRequestResolver(delegate)
                                .resolve(new MockHttpServletRequest());

                assertThat(resolved.getAdditionalParameters())
                                .containsEntry("access_type", "offline")
                                .containsEntry("prompt", "select_account");
        }

        @Test
        void passesThroughNullWhenDelegateDoesNotResolve() {
                OAuth2AuthorizationRequestResolver delegate = mock(OAuth2AuthorizationRequestResolver.class);
                when(delegate.resolve(any(HttpServletRequest.class))).thenReturn(null);

                assertThat(new OAuth2AccountChooserRequestResolver(delegate).resolve(new MockHttpServletRequest()))
                                .isNull();
        }
}
