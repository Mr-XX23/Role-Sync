package com.rolesync.authservice.services.userregistration;

import com.rolesync.authservice.controllers.UserRegistration;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.models.Role;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AuthSecurityEventService;
import com.rolesync.authservice.services.EmailService;
import com.rolesync.authservice.services.OtpService;
import com.rolesync.authservice.services.SmsService;
import com.rolesync.authservice.services.SseNotificationService;
import com.rolesync.authservice.services.user.PasswordPolicy;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.json.JsonMapper;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Public sign-up must never let the caller pick the platform role: whatever the body says, the account is USER.
 * Requests go through the real controller and service; only persistence and messaging are mocked.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class RegistrationRoleTest {

    // Spring MVC reads request bodies with Jackson 3. This mapper also fails on unknown properties,
    // so a passing test shows "role" is skipped on purpose rather than dropped by a lenient mapper.
    private final JsonMapper mapper = JsonMapper.builder()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    @Mock
    private AuthSecurityEventService securityEvents;
    @Mock
    private UserRepository userRepository;
    @Mock
    private EntityManager entityManager;
    @Mock
    private OtpService otpService;
    @Mock
    private EmailService emailService;
    @Mock
    private SmsService smsService;
    @Mock
    private PasswordEncoder passwordEncoder;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        Registration registration = new Registration(securityEvents, userRepository, entityManager, otpService,
                emailService, smsService, passwordEncoder);
        UserRegistration controller = new UserRegistration(registration, mock(SendEmailVerification.class),
                mock(SendPhoneVerification.class), mock(VerifyEmail.class), mock(VerifyPhone.class),
                mock(ResetPassword.class), mock(SseNotificationService.class));
        mvc = MockMvcBuilders.standaloneSetup(controller)
                .setMessageConverters(new JacksonJsonHttpMessageConverter(mapper))
                .build();

        when(passwordEncoder.encode(anyString())).thenReturn("hashed");
        when(userRepository.save(any(AuthUserCredentials.class))).thenAnswer(invocation -> {
            AuthUserCredentials user = invocation.getArgument(0);
            user.setAuthUserId(UUID.randomUUID());
            return user;
        });
    }

    @ParameterizedTest
    @ValueSource(strings = {"SUPER_ADMIN", "ADMIN"})
    void aSignUpAskingForAPrivilegedRoleCreatesAUserAccount(String requestedRole) throws Exception {
        register(signUpBody(requestedRole));

        assertEquals(Role.USER, savedAccount().getRole());
    }

    @ParameterizedTest
    @ValueSource(strings = {"superadmin", "SALESMAN", "not-a-role"})
    void anyOtherRoleValueIsIgnoredToo(String requestedRole) throws Exception {
        register(signUpBody(requestedRole));

        assertEquals(Role.USER, savedAccount().getRole());
    }

    @Test
    void aSignUpWithoutARoleIsAccepted() throws Exception {
        register(signUpBody(null));

        assertEquals(Role.USER, savedAccount().getRole());
    }

    private void register(String body) throws Exception {
        mvc.perform(post("/api/v1/auth/register").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true));
    }

    /** The body the sign-up page sends, with {@code role} set to the given value (left out when null). */
    private String signUpBody(String role) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("username", "New Person");
        body.put("email", "new.person@example.com");
        body.put("password", PasswordPolicy.generateTemporary());
        if (role != null) {
            body.put("role", role);
        }
        body.put("acceptTerms", true);
        body.put("hipaaPrivacyNotice", true);
        return mapper.writeValueAsString(body);
    }

    private AuthUserCredentials savedAccount() {
        ArgumentCaptor<AuthUserCredentials> saved = ArgumentCaptor.forClass(AuthUserCredentials.class);
        verify(userRepository).save(saved.capture());
        return saved.getValue();
    }
}
