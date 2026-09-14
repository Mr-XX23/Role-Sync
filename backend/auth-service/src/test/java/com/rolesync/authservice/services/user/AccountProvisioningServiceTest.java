package com.rolesync.authservice.services.user;

import com.rolesync.authservice.dto.email.EmailResponse;
import com.rolesync.authservice.dto.internal.AccountEmailRequest;
import com.rolesync.authservice.dto.internal.AccountSummary;
import com.rolesync.authservice.dto.internal.EmailOutcome;
import com.rolesync.authservice.dto.internal.ProvisionAccountRequest;
import com.rolesync.authservice.exceptions.BadRequestException;
import com.rolesync.authservice.exceptions.ConflictException;
import com.rolesync.authservice.models.AuthUserCredentials;
import com.rolesync.authservice.models.Role;
import com.rolesync.authservice.repository.UserRepository;
import com.rolesync.authservice.services.AuthSecurityEventService;
import com.rolesync.authservice.services.EmailService;
import com.rolesync.authservice.services.TokenService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.PlatformTransactionManager;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class AccountProvisioningServiceTest {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);

    @Mock
    private UserRepository userRepository;
    @Mock
    private EmailService emailService;
    @Mock
    private TokenService tokenService;
    @Mock
    private AuthSecurityEventService securityEvents;
    @Mock
    private PlatformTransactionManager transactionManager;

    private AccountProvisioningService service;

    private final UUID adminId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        service = new AccountProvisioningService(userRepository, encoder, emailService, tokenService, securityEvents, transactionManager);
        when(emailService.isDeliverableAddress(anyString())).thenReturn(true);
        when(userRepository.saveAndFlush(any(AuthUserCredentials.class))).thenAnswer(invocation -> {
            AuthUserCredentials user = invocation.getArgument(0);
            user.setAuthUserId(UUID.randomUUID());
            return user;
        });
        when(userRepository.save(any(AuthUserCredentials.class))).thenAnswer(invocation -> invocation.getArgument(0));
    }

    private ProvisionAccountRequest request(String email, String name) {
        return ProvisionAccountRequest.builder().email(email).fullName(name).invitedByUserId(adminId).build();
    }

    @Test
    void aNewEmailGetsAVerifiedActiveAccountWaitingForItsFirstPassword() {
        when(userRepository.findFirstByEmailIgnoreCaseOrderByCreatedAtAsc("jane.doe@acme.com")).thenReturn(Optional.empty());

        AccountSummary account = service.provision(request("  Jane.Doe@Acme.com ", "Jane Alexandra Doe-Smithson"), null);

        ArgumentCaptor<AuthUserCredentials> saved = ArgumentCaptor.forClass(AuthUserCredentials.class);
        verify(userRepository).saveAndFlush(saved.capture());
        AuthUserCredentials user = saved.getValue();
        assertEquals("jane.doe@acme.com", user.getEmail());
        assertEquals("Jane Alexandra Doe-S", user.getUsername()); // the column holds 20 characters
        assertTrue(user.isEmailVerified());
        assertEquals(AuthUserCredentials.Status.ACTIVE, user.getStatus());
        assertEquals(AuthUserCredentials.LoginType.EMAIL, user.getLoginType());
        assertEquals(Role.SALESMAN, user.getRole());
        assertTrue(user.requiresPasswordChange());
        assertEquals(adminId, user.getProvisionedBy());
        assertTrue(user.getUsernameId().matches("MS_[A-Z0-9]{8}"));
        assertEquals(Boolean.TRUE, account.getCreated());
        assertTrue(account.isMustChangePassword());
    }

    @Test
    void anExistingAccountIsReturnedUnchanged() {
        AuthUserCredentials existing = AuthUserCredentials.builder()
                .authUserId(UUID.randomUUID()).email("Sam@Acme.com").username("Sam").status(AuthUserCredentials.Status.ACTIVE)
                .isEmailVerified(true).build();
        when(userRepository.findFirstByEmailIgnoreCaseOrderByCreatedAtAsc("sam@acme.com")).thenReturn(Optional.of(existing));

        AccountSummary account = service.provision(request("sam@acme.com", "Samuel"), null);

        assertEquals(Boolean.FALSE, account.getCreated());
        assertEquals(existing.getAuthUserId(), account.getAuthUserId());
        assertFalse(account.isMustChangePassword());
        verify(userRepository, never()).saveAndFlush(any());
    }

    @Test
    void anAddressThatCannotReceiveEmailIsRefused() {
        when(emailService.isDeliverableAddress("someone@tempmail.com")).thenReturn(false);
        assertThrows(BadRequestException.class, () -> service.provision(request("someone@tempmail.com", "Someone"), null));
        verify(userRepository, never()).saveAndFlush(any());
    }

    @Test
    void aTemporaryPasswordIsStoredHashedAndOnlySentByEmail() {
        UUID userId = UUID.randomUUID();
        AuthUserCredentials user = AuthUserCredentials.builder()
                .authUserId(userId).email("jane@acme.com").username("Jane").status(AuthUserCredentials.Status.ACTIVE)
                .passwordHash("unknown").mustChangePassword(true).build();
        when(userRepository.findById(userId)).thenReturn(Optional.of(user));
        when(emailService.sendAccountInvitationEmail(anyString(), anyString(), any(), any(), anyString(), any(), anyBoolean(), eq(userId)))
                .thenReturn(CompletableFuture.completedFuture(EmailResponse.builder().success(true).build()));

        EmailOutcome outcome = service.issueTemporaryPassword(userId,
                AccountEmailRequest.builder().workspaceName("Acme Sales").invitedByName("Rohan").build(), null);

        ArgumentCaptor<String> emailed = ArgumentCaptor.forClass(String.class);
        verify(emailService).sendAccountInvitationEmail(eq("jane@acme.com"), eq("Jane"), eq("Acme Sales"), eq("Rohan"),
                emailed.capture(), any(LocalDateTime.class), eq(false), eq(userId));
        assertTrue(encoder.matches(emailed.getValue(), user.getPasswordHash()));
        assertNotNull(user.getTemporaryPasswordExpiresAt());
        assertTrue(user.getTemporaryPasswordExpiresAt().isAfter(LocalDateTime.now().plusDays(6)));
        verify(tokenService).revokeAllUserTokens(userId);
        assertEquals(EmailOutcome.Status.SENT, outcome.getStatus());
    }

    @Test
    void anAccountWhoseOwnerChoseAPasswordCannotBeReset() {
        UUID userId = UUID.randomUUID();
        AuthUserCredentials user = AuthUserCredentials.builder()
                .authUserId(userId).email("owner@acme.com").passwordHash("their-own").mustChangePassword(null).build();
        when(userRepository.findById(userId)).thenReturn(Optional.of(user));

        assertThrows(ConflictException.class, () -> service.issueTemporaryPassword(userId, new AccountEmailRequest(), null));
        assertEquals("their-own", user.getPasswordHash());
        verify(tokenService, never()).revokeAllUserTokens(any());
        verify(emailService, never()).sendAccountInvitationEmail(any(), any(), any(), any(), any(), any(), anyBoolean(), any());
    }

    @Test
    void emailResultsAreReportedAsSentFailedOrPending() {
        assertEquals(EmailOutcome.Status.SENT, AccountProvisioningService.awaitEmail(
                CompletableFuture.completedFuture(EmailResponse.builder().success(true).build()), Duration.ofSeconds(1), null).getStatus());

        EmailOutcome failed = AccountProvisioningService.awaitEmail(
                CompletableFuture.completedFuture(EmailResponse.builder().success(false).message("Too many emails").build()),
                Duration.ofSeconds(1), null);
        assertEquals(EmailOutcome.Status.FAILED, failed.getStatus());
        assertEquals("Too many emails", failed.getMessage());

        assertEquals(EmailOutcome.Status.PENDING,
                AccountProvisioningService.awaitEmail(new CompletableFuture<>(), Duration.ofMillis(20), null).getStatus());
        assertEquals(EmailOutcome.Status.FAILED, AccountProvisioningService.awaitEmail(
                CompletableFuture.failedFuture(new IllegalStateException("smtp down")), Duration.ofSeconds(1), null).getStatus());
    }

    @Test
    void usernamesFallBackToTheEmailAndFitTheColumn() {
        assertEquals("jane", AccountProvisioningService.usernameFrom("   ", "jane@acme.com"));
        assertEquals("Jane Doe", AccountProvisioningService.usernameFrom(" Jane \n Doe ", "jane@acme.com"));
        assertEquals(20, AccountProvisioningService.usernameFrom("x".repeat(40), "jane@acme.com").length());
        assertEquals("User", AccountProvisioningService.usernameFrom(null, null));
    }
}
