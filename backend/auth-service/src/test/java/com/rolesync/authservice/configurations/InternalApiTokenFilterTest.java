package com.rolesync.authservice.configurations;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class InternalApiTokenFilterTest {

    private static MockHttpServletRequest request(String path, String token) {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", path);
        if (token != null) {
            request.addHeader(InternalApiTokenFilter.TOKEN_HEADER, token);
        }
        return request;
    }

    @Test
    void theRightTokenReachesTheInternalApi() throws Exception {
        MockFilterChain chain = new MockFilterChain();
        MockHttpServletResponse response = new MockHttpServletResponse();
        new InternalApiTokenFilter("s3cret").doFilter(request("/internal/v1/accounts/lookup", "s3cret"), response, chain);
        assertNotNull(chain.getRequest());
        assertEquals(200, response.getStatus());
    }

    @Test
    void aMissingOrWrongTokenIsRejected() throws Exception {
        for (String token : new String[] {null, "", "wrong", "s3cret-but-longer"}) {
            MockFilterChain chain = new MockFilterChain();
            MockHttpServletResponse response = new MockHttpServletResponse();
            new InternalApiTokenFilter("s3cret").doFilter(request("/internal/v1/accounts/provision", token), response, chain);
            assertNull(chain.getRequest(), "token " + token);
            assertEquals(401, response.getStatus());
        }
    }

    @Test
    void withoutAConfiguredTokenTheInternalApiIsOff() throws Exception {
        MockFilterChain chain = new MockFilterChain();
        MockHttpServletResponse response = new MockHttpServletResponse();
        new InternalApiTokenFilter("  ").doFilter(request("/internal/v1/accounts/provision", ""), response, chain);
        assertNull(chain.getRequest());
        assertEquals(503, response.getStatus());
    }

    @Test
    void otherPathsAreNotTouched() throws Exception {
        MockFilterChain chain = new MockFilterChain();
        MockHttpServletResponse response = new MockHttpServletResponse();
        new InternalApiTokenFilter("s3cret").doFilter(request("/api/v1/auth/login", null), response, chain);
        assertNotNull(chain.getRequest());
    }
}
