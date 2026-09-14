package com.role_sync.billing.controllers;

import com.role_sync.billing.dto.AdminDtos.AccountDetailResponse;
import com.role_sync.billing.dto.AdminDtos.AccountResponse;
import com.role_sync.billing.dto.AdminDtos.AdjustRequest;
import com.role_sync.billing.dto.AdminDtos.OverviewResponse;
import com.role_sync.billing.dto.AdminDtos.PageResponse;
import com.role_sync.billing.dto.AdminDtos.StatusRequest;
import com.role_sync.billing.dto.AdminDtos.UsageBreakdownResponse;
import com.role_sync.billing.dto.PaymentOrderResponse;
import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.models.CreditAccountStatus;
import com.role_sync.billing.models.PaymentOrder;
import com.role_sync.billing.models.PaymentStatus;
import com.role_sync.billing.repository.CreditAccountRepository;
import com.role_sync.billing.repository.PaymentOrderRepository;
import com.role_sync.billing.security.PlatformAdminGuard;
import com.role_sync.billing.security.PlatformAdminGuard.Actor;
import com.role_sync.billing.services.CreditLedgerService;
import com.role_sync.billing.services.UsageReportService;
import com.role_sync.billing.utils.CallerIdentity;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.UUID;

/** Revenue, usage and credit operations for platform super admins. */
@RestController
@RequestMapping("/api/v1/billing/admin")
public class AdminBillingController {

	private static final int MAX_PAGE_SIZE = 100;

	private final PlatformAdminGuard admins;
	private final CreditLedgerService ledger;
	private final UsageReportService reports;
	private final CreditAccountRepository accounts;
	private final PaymentOrderRepository orders;

	public AdminBillingController(PlatformAdminGuard admins, CreditLedgerService ledger, UsageReportService reports,
	                              CreditAccountRepository accounts, PaymentOrderRepository orders) {
		this.admins = admins;
		this.ledger = ledger;
		this.reports = reports;
		this.accounts = accounts;
		this.orders = orders;
	}

	@GetMapping("/overview")
	public ResponseEntity<OverviewResponse> overview(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestParam(value = "days", required = false) Integer days) {
		requireAdmin(userIdHeader);
		return ResponseEntity.ok(reports.overview(UsageReportService.clampDays(days)));
	}

	@GetMapping("/accounts")
	public ResponseEntity<PageResponse<AccountResponse>> accounts(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestParam(value = "query", required = false) String query,
			@RequestParam(value = "status", required = false) CreditAccountStatus status,
			@RequestParam(value = "page", defaultValue = "0") int page,
			@RequestParam(value = "size", defaultValue = "20") int size) {
		requireAdmin(userIdHeader);
		// Never null: Postgres cannot type a null text parameter inside lower(...) and fails the query.
		String cleanQuery = query == null ? "" : query.trim().toLowerCase(java.util.Locale.ROOT);
		Page<CreditAccount> result = accounts.search(cleanQuery, status, pageRequest(page, size));
		return ResponseEntity.ok(new PageResponse<>(
				result.getContent().stream().map(AccountResponse::from).toList(),
				result.getNumber(), result.getSize(), result.getTotalElements()));
	}

	@GetMapping("/accounts/{workspaceId}")
	public ResponseEntity<AccountDetailResponse> account(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID workspaceId) {
		requireAdmin(userIdHeader);
		CreditAccount account = accounts.findById(workspaceId)
				.orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND,
						"This workspace has no credit account yet. It is created the first time the workspace is used."));
		return ResponseEntity.ok(reports.accountDetail(account, 50));
	}

	@PostMapping("/accounts/{workspaceId}/grant")
	public ResponseEntity<AccountResponse> grant(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID workspaceId,
			@RequestBody AdjustRequest request) {
		Actor actor = requireAdmin(userIdHeader);
		AdjustRequest body = requireBody(request);
		return ResponseEntity.ok(AccountResponse.from(
				ledger.adminGrant(workspaceId, body.credits(), body.reason(), actor.authUserId())));
	}

	@PostMapping("/accounts/{workspaceId}/deduct")
	public ResponseEntity<AccountResponse> deduct(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID workspaceId,
			@RequestBody AdjustRequest request) {
		Actor actor = requireAdmin(userIdHeader);
		AdjustRequest body = requireBody(request);
		return ResponseEntity.ok(AccountResponse.from(ledger.adminDeduct(workspaceId, body.credits(), body.reason(),
				actor.authUserId(), Boolean.TRUE.equals(body.allowNegative()))));
	}

	@PostMapping("/accounts/{workspaceId}/suspend")
	public ResponseEntity<AccountResponse> suspend(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID workspaceId,
			@RequestBody StatusRequest request) {
		Actor actor = requireAdmin(userIdHeader);
		String reason = request == null ? null : request.reason();
		return ResponseEntity.ok(AccountResponse.from(ledger.suspend(workspaceId, reason, actor.authUserId())));
	}

	@PostMapping("/accounts/{workspaceId}/reactivate")
	public ResponseEntity<AccountResponse> reactivate(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@PathVariable UUID workspaceId,
			@RequestBody StatusRequest request) {
		Actor actor = requireAdmin(userIdHeader);
		String reason = request == null ? null : request.reason();
		return ResponseEntity.ok(AccountResponse.from(ledger.reactivate(workspaceId, reason, actor.authUserId())));
	}

	@GetMapping("/payments")
	public ResponseEntity<PageResponse<PaymentOrderResponse>> payments(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestParam(value = "status", required = false) PaymentStatus status,
			@RequestParam(value = "page", defaultValue = "0") int page,
			@RequestParam(value = "size", defaultValue = "20") int size) {
		requireAdmin(userIdHeader);
		PageRequest pageable = pageRequest(page, size);
		Page<PaymentOrder> result = status == null
				? orders.findAllByOrderByCreatedAtDesc(pageable)
				: orders.findByStatusOrderByCreatedAtDesc(status, pageable);
		return ResponseEntity.ok(new PageResponse<>(
				result.getContent().stream().map(PaymentOrderResponse::from).toList(),
				result.getNumber(), result.getSize(), result.getTotalElements()));
	}

	@GetMapping("/usage")
	public ResponseEntity<UsageBreakdownResponse> usage(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestParam(value = "days", required = false) Integer days,
			@RequestParam(value = "workspaceId", required = false) UUID workspaceId) {
		requireAdmin(userIdHeader);
		return ResponseEntity.ok(reports.breakdown(UsageReportService.clampDays(days), workspaceId));
	}

	private Actor requireAdmin(String userIdHeader) {
		return admins.requireSuperAdmin(CallerIdentity.requireUserId(userIdHeader));
	}

	private static AdjustRequest requireBody(AdjustRequest request) {
		if (request == null) {
			throw new IllegalArgumentException("Send credits and a reason.");
		}
		return request;
	}

	private static PageRequest pageRequest(int page, int size) {
		return PageRequest.of(Math.max(0, page), Math.min(Math.max(1, size), MAX_PAGE_SIZE));
	}
}
