package com.role_sync.billing.controllers;

import com.role_sync.billing.configurations.BillingProperties;
import com.role_sync.billing.dto.CreditDtos.CreditBalanceResponse;
import com.role_sync.billing.dto.CreditDtos.UsageSummaryResponse;
import com.role_sync.billing.models.CreditAccount;
import com.role_sync.billing.security.WorkspaceMembershipGuard;
import com.role_sync.billing.services.CreditLedgerService;
import com.role_sync.billing.services.UsageReportService;
import com.role_sync.billing.utils.CallerIdentity;
import com.role_sync.billing.utils.CreditMath;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

/** A workspace's balance for the top bar, and its usage for the credits page. */
@RestController
@RequestMapping("/api/v1/billing")
public class CreditController {

	private final CreditLedgerService ledger;
	private final UsageReportService reports;
	private final WorkspaceMembershipGuard membership;
	private final BillingProperties properties;

	public CreditController(CreditLedgerService ledger, UsageReportService reports,
	                        WorkspaceMembershipGuard membership, BillingProperties properties) {
		this.ledger = ledger;
		this.reports = reports;
		this.membership = membership;
		this.properties = properties;
	}

	@GetMapping("/credits")
	public ResponseEntity<CreditBalanceResponse> credits(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
			@RequestParam(value = "workspaceId", required = false) UUID workspaceParam) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);
		UUID workspaceId = CallerIdentity.requireWorkspaceId(tenantHeader, workspaceParam);
		membership.requireMember(userId, workspaceId);

		CreditAccount account = ledger.ensureAccount(workspaceId, userId);
		long threshold = properties.getCredits().getLowBalanceThreshold();
		return ResponseEntity.ok(new CreditBalanceResponse(
				workspaceId,
				CreditMath.toCredits(account.getBalanceMillicredits()),
				account.getStatus(),
				account.getBalanceMillicredits() < CreditMath.wholeCreditsToMillicredits(threshold),
				threshold,
				CreditMath.toCredits(account.getLifetimeCreditedMillicredits()),
				CreditMath.toCredits(account.getLifetimeUsedMillicredits())));
	}

	@GetMapping("/usage/summary")
	public ResponseEntity<UsageSummaryResponse> usageSummary(
			@RequestHeader(value = "X-User-Id", required = false) String userIdHeader,
			@RequestHeader(value = "X-Tenant-Id", required = false) String tenantHeader,
			@RequestParam(value = "workspaceId", required = false) UUID workspaceParam,
			@RequestParam(value = "days", required = false) Integer days) {

		UUID userId = CallerIdentity.requireUserId(userIdHeader);
		UUID workspaceId = CallerIdentity.requireWorkspaceId(tenantHeader, workspaceParam);
		membership.requireMember(userId, workspaceId);

		CreditAccount account = ledger.ensureAccount(workspaceId, userId);
		return ResponseEntity.ok(reports.summary(account, UsageReportService.clampDays(days)));
	}
}
