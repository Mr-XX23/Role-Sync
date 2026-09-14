package com.role_sync.billing.controllers;

import com.role_sync.billing.dto.CreditDtos.CheckResponse;
import com.role_sync.billing.dto.CreditDtos.UsageItemRequest;
import com.role_sync.billing.dto.CreditDtos.UsageRequest;
import com.role_sync.billing.dto.CreditDtos.UsageResponse;
import com.role_sync.billing.dto.UsageItem;
import com.role_sync.billing.models.UsageCategory;
import com.role_sync.billing.security.InternalTokenGuard;
import com.role_sync.billing.services.CreditLedgerService;
import com.role_sync.billing.services.CreditLedgerService.CheckResult;
import com.role_sync.billing.services.CreditLedgerService.UsageCommand;
import com.role_sync.billing.services.CreditLedgerService.UsageResult;
import com.role_sync.billing.utils.CreditMath;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * How the agent and data-pipeline ask "may this workspace spend?" and report what an operation
 * used. Reached directly on the docker network with the shared internal token; the gateway does
 * not route it.
 */
@RestController
@RequestMapping("/internal/v1/billing")
public class InternalBillingController {

	private final CreditLedgerService ledger;
	private final InternalTokenGuard internal;

	public InternalBillingController(CreditLedgerService ledger, InternalTokenGuard internal) {
		this.ledger = ledger;
		this.internal = internal;
	}

	@GetMapping("/credits/{workspaceId}/check")
	public ResponseEntity<CheckResponse> check(
			@RequestHeader(value = "X-Internal-Token", required = false) String token,
			@PathVariable UUID workspaceId,
			@RequestParam(value = "userId", required = false) UUID userId) {

		internal.require(token);
		CheckResult result = ledger.check(workspaceId, userId);
		return ResponseEntity.ok(new CheckResponse(result.allowed(), result.code(),
				CreditMath.toCredits(result.balanceMillicredits()), result.status()));
	}

	@PostMapping("/usage")
	public ResponseEntity<UsageResponse> usage(
			@RequestHeader(value = "X-Internal-Token", required = false) String token,
			@RequestBody UsageRequest request) {

		internal.require(token);
		if (request == null) {
			throw new IllegalArgumentException("A usage body is required");
		}
		UsageCommand command = new UsageCommand(
				request.workspaceId(),
				request.userId(),
				request.operation(),
				UsageCategory.parse(request.category()),
				request.idempotencyKey(),
				request.reference(),
				toItems(request.items()),
				request.metadata());
		UsageResult result;
		try {
			result = ledger.recordUsage(command);
		}
		catch (DataIntegrityViolationException raced) {
			// A concurrent request recorded the same key first: to the caller that is a replay, so answer
			// "duplicate" instead of an error its retry queue would have to interpret.
			if (!ledger.isUsageRecorded(command.idempotencyKey())) {
				throw raced;
			}
			result = ledger.alreadyRecorded(command.workspaceId());
		}

		return ResponseEntity.ok(new UsageResponse(
				CreditMath.toCredits(result.millicreditsCharged()),
				result.costUsd(),
				CreditMath.toCredits(result.balanceMillicredits()),
				result.status(),
				result.duplicate()));
	}

	private static List<UsageItem> toItems(List<UsageItemRequest> items) {
		if (items == null) {
			return List.of();
		}
		List<UsageItem> result = new ArrayList<>(items.size());
		for (UsageItemRequest item : items) {
			if (item == null || item.type() == null) {
				throw new IllegalArgumentException("every item needs a type of TOKENS or UNITS");
			}
			switch (item.type().trim().toUpperCase()) {
				case "TOKENS" -> result.add(UsageItem.tokens(
						item.model(),
						value(item.inputTokens()),
						value(item.cachedInputTokens()),
						value(item.outputTokens())));
				case "UNITS" -> result.add(UsageItem.units(
						item.unit(),
						item.quantity() == null ? BigDecimal.ONE : item.quantity()));
				default -> throw new IllegalArgumentException("unknown item type " + item.type());
			}
		}
		return result;
	}

	private static long value(Long tokens) {
		return tokens == null ? 0L : tokens;
	}
}
