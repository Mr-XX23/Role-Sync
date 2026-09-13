import os
import json
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

# Supported Sales Taxonomy Categories
VALID_SALES_CATEGORIES = {
    "BATTLECARD",
    "PRICING_PACKAGING",
    "CASE_STUDY_ROI",
    "SECURITY_COMPLIANCE",
    "PRODUCT_SPEC",
    "CONTRACT_LEGAL",
    "GENERAL_RESOURCE",
}

# ---------------------------------------------------------------------------
# Dynamic content sampling for classification
# ---------------------------------------------------------------------------
# Defaults (all overridable via env). Kept intentionally small: the classifier
# only needs a REPRESENTATIVE overview of a document to categorize it, never the
# full text — this is what caps LLM token cost. max_chars is derived from a token
# budget and must stay well within the OpenRouter model's input-context window.
DEFAULT_CLASSIFICATION_MAX_TOKENS = 4000   # hard classification input budget (tokens)
DEFAULT_CHARS_PER_TOKEN = 4                # rough heuristic (~4 chars per token)
DEFAULT_MIN_CHUNK_CHARS = 500              # smallest useful sample region
DEFAULT_MAX_REGIONS = 12                   # cap on number of sampled regions
DEFAULT_REGION_STRIDE_CHARS = 6000         # ~one region per this many chars, before capping

_SAMPLE_SEPARATOR = "\n\n[...]\n\n"

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# What a single classification request concluded, when it did not produce a result.
_RETRY = "retry"          # worth asking again (the free router may pick another model)
_NEXT_MODEL = "next"      # this model cannot serve the request; move on
_STOP = "stop"            # no model will succeed (daily limit, bad key): use the heuristic


def classification_response_schema() -> dict[str, Any]:
    """The JSON schema every classification reply must satisfy.

    Sent as an enforced response format, so the reply is guaranteed to be valid
    JSON with a known category. Free models used to answer in prose, run out of
    tokens mid-object, or wrap JSON in markdown; each of those was silently
    discarded and the document fell through to the keyword rules.
    """
    return {
        "name": "sales_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "category", "target_competitor", "target_industry",
                "sales_summary", "sales_tags", "confidence_score",
            ],
            "properties": {
                "category": {"type": "string", "enum": sorted(VALID_SALES_CATEGORIES)},
                "target_competitor": {"type": ["string", "null"]},
                "target_industry": {"type": ["string", "null"]},
                "sales_summary": {"type": "string"},
                "sales_tags": {"type": "array", "items": {"type": "string"}},
                "confidence_score": {"type": "number"},
            },
        },
    }


def _parse_json_object(content: str) -> Optional[dict[str, Any]]:
    """Extract the JSON object from a reply, tolerating reasoning tags and fences."""
    text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _env_models(name: str) -> list[str]:
    return [m.strip() for m in os.environ.get(name, "").split(",") if m.strip()]


def _env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.environ.get(name, "")).strip())
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def build_classification_content(
    text: str,
    *,
    max_chars: int,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    max_regions: int = DEFAULT_MAX_REGIONS,
    region_stride_chars: int = DEFAULT_REGION_STRIDE_CHARS,
    separator: str = _SAMPLE_SEPARATOR,
) -> str:
    """
    Build a representative, budget-bounded classification input from a document.

    Strategy:
      * Short document (<= max_chars): used in full, no sampling.
      * Larger document: sampled DETERMINISTICALLY from evenly-spaced regions that
        span the beginning, middle(s) and end. The number of regions scales with
        the document size (~one per region_stride_chars) up to max_regions, and the
        total sampled length (including separators) never exceeds max_chars.

    The same logic works for 1K, 10K, 100K, 1M+ character documents: bigger docs get
    more regions (each region a smaller slice of the fixed budget), so the classifier
    always sees the whole document without ever exceeding the token budget.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if max_chars <= 0 or len(text) <= max_chars:
        return text  # short enough — classify on the entire document

    sep_len = len(separator)

    # How many regions the budget can afford at the minimum chunk size (separators
    # included). Guarantees chunk_size >= min_chunk_chars and total <= max_chars.
    affordable = max(1, (max_chars + sep_len) // (min_chunk_chars + sep_len))

    # Region count scales with document size, then is bounded by max_regions and
    # by what the budget can actually afford.
    regions = round(len(text) / max(1, region_stride_chars))
    regions = max(3, min(max_regions, regions))
    regions = max(1, min(regions, affordable))

    sep_overhead = sep_len * (regions - 1)
    content_budget = max(min_chunk_chars, max_chars - sep_overhead)
    chunk_size = max(min_chunk_chars, content_budget // regions)

    if regions == 1:
        positions = [0]
    else:
        step = (len(text) - chunk_size) / (regions - 1)
        positions = [round(i * step) for i in range(regions)]

    chunks = []
    for pos in positions:
        start = max(0, min(pos, len(text) - chunk_size))
        chunks.append(text[start:start + chunk_size])

    return separator.join(chunks)

class SalesClassificationResult(BaseModel):
    category: str = "GENERAL_RESOURCE"
    target_competitor: Optional[str] = None
    target_industry: Optional[str] = None
    sales_summary: str = ""
    sales_tags: list[str] = Field(default_factory=list)
    confidence_score: float = 0.5
    classifier_used: str = "heuristic_rule_engine"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "target_competitor": self.target_competitor,
            "target_industry": self.target_industry,
            "sales_summary": self.sales_summary,
            "sales_tags": self.sales_tags,
            "confidence_score": self.confidence_score,
            "classifier_used": self.classifier_used,
        }


class SalesClassifier:
    """
    Intelligent Sales Document Classifier for the RoleSync Knowledge Vault.
    Uses OpenRouter - by default the openrouter/free router, which picks an available
    free model per request - with an enforced JSON schema, and falls back to a
    deterministic keyword rule engine when no model can classify.
    """

    KNOWN_COMPETITORS = [
        "Salesforce", "HubSpot", "Zendesk", "ServiceNow", "Workday",
        "Jira", "Asana", "Monday.com", "ClickUp", "Notion",
        "Slack", "Microsoft Teams", "Zoom", "Gong", "Chorus",
        "Outreach", "SalesLoft", "Apollo", "ZoomInfo", "Stripe",
        "Snowflake", "Datadog", "Dynatrace", "Splunk", "AWS", "Google Cloud"
    ]

    KNOWN_INDUSTRIES = [
        "Healthcare", "Fintech", "Financial Services", "Banking", "Insurance",
        "E-commerce", "Retail", "Enterprise SaaS", "Cybersecurity", "Manufacturing",
        "Logistics & Supply Chain", "Education / EdTech", "Real Estate", "Media & Entertainment",
        "Government / Public Sector", "Telecommunications"
    ]

    def __init__(self) -> None:
        self.api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPEN_ROUTER_API")
            or os.environ.get("OPENROUTER_API")
            or ""
        ).strip()
        # openrouter/free picks an available free model per request, filtered to
        # models that support what the request requires (see _request_classification).
        self.model_name = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
        # Optional extra models to try, in order, if the primary cannot classify.
        self.fallback_models = _env_models("OPENROUTER_FALLBACK_MODELS")
        self.attempts_per_model = _env_int("CLASSIFIER_ATTEMPTS_PER_MODEL", 2)
        self.request_timeout = _env_int("CLASSIFIER_TIMEOUT_SECONDS", 25)
        # Room to finish: reasoning models used to spend a 400-token budget thinking
        # and get cut off before writing the JSON.
        self.max_output_tokens = _env_int("CLASSIFIER_MAX_OUTPUT_TOKENS", 1024)
        self.site_url = os.environ.get("OPENROUTER_SITE_URL", "https://rolesync.ai")
        self.site_name = os.environ.get("OPENROUTER_SITE_NAME", "RoleSync Enterprise AI")

        # Classification content-sampling budget (env-overridable). max_chars is the
        # hard cap on how much document text is ever sent to the classifier.
        self.max_classification_tokens = _env_int("CLASSIFICATION_MAX_TOKENS", DEFAULT_CLASSIFICATION_MAX_TOKENS)
        self.chars_per_token = _env_int("CLASSIFICATION_CHARS_PER_TOKEN", DEFAULT_CHARS_PER_TOKEN)
        self.max_classification_chars = self.max_classification_tokens * self.chars_per_token
        self.min_chunk_chars = _env_int("CLASSIFICATION_MIN_CHUNK_CHARS", DEFAULT_MIN_CHUNK_CHARS)
        self.max_regions = _env_int("CLASSIFICATION_MAX_REGIONS", DEFAULT_MAX_REGIONS)
        self.region_stride_chars = _env_int("CLASSIFICATION_REGION_STRIDE_CHARS", DEFAULT_REGION_STRIDE_CHARS)

    def classify(
        self,
        filename: str,
        mime_type: str = "text/plain",
        text_content: str = "",
        user_override_category: Optional[str] = None,
        user_override_competitor: Optional[str] = None,
    ) -> SalesClassificationResult:
        """
        Classifies the document into a sales taxonomy category and extracts sales intelligence.
        Applies user overrides if provided.
        """
        # If user explicitly specified category, honor it as highest priority
        if user_override_category and user_override_category.upper() in VALID_SALES_CATEGORIES:
            result = self._classify_with_ai_or_heuristic(filename, mime_type, text_content)
            result.category = user_override_category.upper()
            if user_override_competitor:
                result.target_competitor = user_override_competitor
            result.confidence_score = 1.0
            return result

        # Run AI classification if API key is present, otherwise fallback to heuristics
        result = self._classify_with_ai_or_heuristic(filename, mime_type, text_content)
        if user_override_competitor:
            result.target_competitor = user_override_competitor
        return result

    def classify_preliminary(
        self,
        filename: str,
        text_content: str = "",
        user_override_category: Optional[str] = None,
        user_override_competitor: Optional[str] = None,
    ) -> SalesClassificationResult:
        """An instant placeholder label shown while a document is still processing.

        Uses only the keyword rules. The upload request used to run the full model
        classification on the filename alone - which tells a model almost nothing,
        held the request for many seconds, and spent a request from a shared daily
        allowance before the real classification spent another. The document is
        classified properly, once, after it has been parsed.
        """
        result = self._heuristic_classification(filename, text_content or filename)
        if user_override_category and user_override_category.upper() in VALID_SALES_CATEGORIES:
            result.category = user_override_category.upper()
            result.confidence_score = 1.0
        if user_override_competitor:
            result.target_competitor = user_override_competitor
        return result

    def _classify_with_ai_or_heuristic(
        self,
        filename: str,
        mime_type: str,
        text_content: str,
    ) -> SalesClassificationResult:
        # Check if OpenRouter key is available
        api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPEN_ROUTER_API")
            or os.environ.get("OPENROUTER_API")
            or self.api_key
        ).strip()

        if api_key:
            try:
                ai_result = self._call_openrouter_classifier(api_key, filename, mime_type, text_content)
                if ai_result:
                    return ai_result
            except Exception as err:
                print(f"[SalesClassifier] OpenRouter classification failed ({err}). Running heuristic rule fallback.")

        # Fallback to local heuristic rule engine
        return self._heuristic_classification(filename, text_content)

    def _call_openrouter_classifier(
        self,
        api_key: str,
        filename: str,
        mime_type: str,
        text_content: str,
    ) -> Optional[SalesClassificationResult]:
        import requests

        # Build a representative, budget-bounded classification input. Short docs are
        # used whole; larger docs are sampled across beginning/middle/end so the
        # classifier sees the entire document without exceeding the token budget.
        snippet = build_classification_content(
            text_content or "",
            max_chars=self.max_classification_chars,
            min_chunk_chars=self.min_chunk_chars,
            max_regions=self.max_regions,
            region_stride_chars=self.region_stride_chars,
        )
        if not snippet and not filename:
            return None

        system_prompt = (
            "You are an expert Enterprise Sales Intelligence Specialist and Sales Knowledge Librarian. "
            "Analyze the provided business document title and content (which may be representative excerpts "
            "sampled from across the whole document), and classify it into exactly ONE sales category.\n\n"
            "Categories available:\n"
            "- BATTLECARD: Competitor comparison, objection handling, win/loss strategies, competitor weaknesses/strengths.\n"
            "- PRICING_PACKAGING: Rate cards, discounting rules, tier packaging, quotes, licensing fees, seat costs.\n"
            "- CASE_STUDY_ROI: Customer success metrics, client logos, case studies, quantified ROI proof, testimonials.\n"
            "- SECURITY_COMPLIANCE: SOC2, ISO27001, GDPR, HIPAA, compliance whitepapers, security architecture, data privacy.\n"
            "- PRODUCT_SPEC: Technical specs, API docs, system architecture, feature deep-dives, developer guides.\n"
            "- CONTRACT_LEGAL: MSAs, SLAs, DPAs, order forms, terms of service, indemnification, liability.\n"
            "- GENERAL_RESOURCE: General company material or miscellaneous not fitting the above categories.\n\n"
            "Rules:\n"
            "- Personal documents (resumes/CVs), internal notes and anything not written to help sell are GENERAL_RESOURCE.\n"
            "- target_competitor is a rival vendor the document positions against. A tool or product that someone "
            "merely uses, lists as a skill, or integrates with is NOT a competitor - use null.\n"
            "- target_industry is the customer industry the document targets, or null.\n"
            "- sales_summary is 1-2 sentences on what the document gives a sales rep; sales_tags has at most 6 short tags.\n"
            "Reply with only the JSON object."
        )

        user_content = (
            f"Filename: {filename}\n"
            f"MIME Type: {mime_type}\n"
            f"Representative content samples (may span the beginning, middle and end of the document):\n{snippet}"
        )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
            "Content-Type": "application/json",
        }

        candidates: list[str] = []
        for model in [self.model_name, *self.fallback_models]:
            if model and model not in candidates:
                candidates.append(model)

        for model in candidates:
            for attempt in range(1, self.attempts_per_model + 1):
                outcome = self._request_classification(
                    requests, headers, model, system_prompt, user_content, filename, attempt
                )
                if isinstance(outcome, SalesClassificationResult):
                    return outcome
                if outcome == _STOP:
                    return None
                if outcome == _NEXT_MODEL:
                    break
        return None

    def _request_classification(
        self,
        requests_module,
        headers: dict[str, str],
        model: str,
        system_prompt: str,
        user_content: str,
        filename: str,
        attempt: int,
    ):
        """One classification request. Returns a result, or why it produced none.

        Every rejected reply is logged with its reason: a 200 response that could
        not be used used to be skipped silently, which hid which models worked.
        """
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
            # The reply must be valid JSON matching the classification schema...
            "response_format": {"type": "json_schema", "json_schema": classification_response_schema()},
            # ...and only models whose providers honour every parameter here may
            # serve it, so openrouter/free never routes to one that ignores the schema.
            "provider": {"require_parameters": True},
            # A classification does not need a chain of thought, and reasoning is
            # what used to exhaust the token budget before any answer was written.
            "reasoning": {"enabled": False},
        }
        label = f"{model} (attempt {attempt}/{self.attempts_per_model})"

        try:
            resp = requests_module.post(_OPENROUTER_URL, headers=headers, json=body, timeout=self.request_timeout)
        except Exception as err:
            print(f"[SalesClassifier] {label} request failed: {type(err).__name__}")
            return _RETRY

        if resp.status_code != 200:
            detail = (resp.text or "")[:160]
            if resp.status_code == 429 and "free-models-per-day" in detail:
                # Every free model draws on the same daily allowance, so trying others
                # only delays the fallback.
                print("[SalesClassifier] OpenRouter free-model daily limit reached; "
                      "using keyword rules until it resets.")
                return _STOP
            if resp.status_code in (401, 402):
                print(f"[SalesClassifier] OpenRouter rejected the API key or account (HTTP {resp.status_code}): {detail}")
                return _STOP
            if resp.status_code in (400, 403, 404):
                print(f"[SalesClassifier] {label} cannot serve this request (HTTP {resp.status_code}): {detail}")
                return _NEXT_MODEL
            print(f"[SalesClassifier] {label} HTTP {resp.status_code}: {detail}")
            return _RETRY

        try:
            data = resp.json()
        except ValueError:
            print(f"[SalesClassifier] {label} returned a non-JSON response body")
            return _RETRY

        served = data.get("model") or model
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
        finish = choice.get("finish_reason")

        if not content:
            print(f"[SalesClassifier] {label} served by {served} returned no content (finish={finish}); rejected")
            return _RETRY

        parsed = _parse_json_object(content)
        if parsed is None:
            print(f"[SalesClassifier] {label} served by {served} returned unusable output "
                  f"(finish={finish}): {content[:100]!r}; rejected")
            return _RETRY

        category = str(parsed.get("category", "")).upper().strip()
        if category not in VALID_SALES_CATEGORIES:
            print(f"[SalesClassifier] {label} served by {served} returned unknown category {category!r}; rejected")
            return _RETRY

        competitor = parsed.get("target_competitor")
        if competitor is not None and str(competitor).strip().lower() in ("", "null", "none"):
            competitor = None
        industry = parsed.get("target_industry")
        if industry is not None and str(industry).strip().lower() in ("", "null", "none"):
            industry = None

        raw_tags = parsed.get("sales_tags") or []
        tags = [str(t).strip() for t in raw_tags if str(t).strip()][:6] if isinstance(raw_tags, list) else []
        try:
            confidence = max(0.0, min(1.0, float(parsed.get("confidence_score", 0.9))))
        except (TypeError, ValueError):
            confidence = 0.9

        # Record which model actually classified the document: openrouter/free picks
        # one per request, and a poor classification is only diagnosable if you can
        # see which model made it.
        used = f"openrouter:{served}" if served == model else f"openrouter:{model}->{served}"
        print(f"[SalesClassifier] Classified '{filename}' as {category} via {used}")
        return SalesClassificationResult(
            category=category,
            target_competitor=str(competitor).strip() if competitor else None,
            target_industry=str(industry).strip() if industry else None,
            sales_summary=str(parsed.get("sales_summary") or "").strip() or f"Sales resource: {filename}",
            sales_tags=tags,
            confidence_score=confidence,
            classifier_used=used,
        )

    def _heuristic_classification(self, filename: str, text_content: str) -> SalesClassificationResult:
        """
        Fast, deterministic heuristic rule engine using keyword patterns, filename analysis,
        and known competitor / industry entity matching.
        """
        lower_fn = filename.lower()
        lower_text = (text_content or "").lower()[:6000]
        combined = f"{lower_fn}\n{lower_text}"

        # 1. Detect Competitor
        detected_competitor = None
        for comp in self.KNOWN_COMPETITORS:
            pattern = rf"\b{re.escape(comp.lower())}\b"
            if re.search(pattern, combined):
                detected_competitor = comp
                break

        # 2. Detect Industry
        detected_industry = None
        for ind in self.KNOWN_INDUSTRIES:
            if ind.lower() in combined:
                detected_industry = ind
                break

        # 3. Score Categories
        scores = {cat: 0 for cat in VALID_SALES_CATEGORIES}

        # BATTLECARD
        battlecard_signals = [
            "battlecard", "battle card", "competitor", "vs ", "versus",
            "differentiator", "kill sheet", "objection handling", "rebuttal",
            "why we win", "where they win", "landmine", "feature shootout",
            "beats ", "outperforms", "pitching against", "alternative to", "comparison"
        ]
        for sig in battlecard_signals:
            if sig in lower_fn:
                scores["BATTLECARD"] += 5
            if sig in lower_text:
                scores["BATTLECARD"] += 2
        if detected_competitor and ("vs" in lower_fn or "battlecard" in lower_fn or "comparison" in lower_fn):
            scores["BATTLECARD"] += 6

        # PRICING_PACKAGING
        pricing_signals = [
            "pricing", "rate card", "price list", "packaging", "subscription tier",
            "per user", "per month", "per seat", "discount", "quote", "enterprise tier",
            "starter tier", "billing cycle", "arr", "acv", "payment schedule", "license fee"
        ]
        for sig in pricing_signals:
            if sig in lower_fn:
                scores["PRICING_PACKAGING"] += 5
            if sig in lower_text:
                scores["PRICING_PACKAGING"] += 2

        # CASE_STUDY_ROI
        case_study_signals = [
            "case study", "customer story", "success story", "roi", "return on investment",
            "client story", "testimonial", "customer spotlight", "saved 40%", "increased conversion",
            "efficiency gain", "metrics gained", "benchmark results"
        ]
        for sig in case_study_signals:
            if sig in lower_fn:
                scores["CASE_STUDY_ROI"] += 5
            if sig in lower_text:
                scores["CASE_STUDY_ROI"] += 2

        # SECURITY_COMPLIANCE
        security_signals = [
            "soc 2", "soc2", "iso 27001", "iso27001", "gdpr", "hipaa", "compliance",
            "penetration test", "pen test", "data privacy", "encryption at rest", "cve",
            "security whitepaper", "access control", "audit report", "subprocessor"
        ]
        for sig in security_signals:
            if sig in lower_fn:
                scores["SECURITY_COMPLIANCE"] += 5
            if sig in lower_text:
                scores["SECURITY_COMPLIANCE"] += 2

        # PRODUCT_SPEC
        spec_signals = [
            "spec", "specification", "architecture", "api documentation", "api endpoint",
            "technical requirement", "data model", "schema", "sdk", "webhook", "payload",
            "release notes", "system architecture", "latency benchmark"
        ]
        for sig in spec_signals:
            if sig in lower_fn:
                scores["PRODUCT_SPEC"] += 5
            if sig in lower_text:
                scores["PRODUCT_SPEC"] += 2

        # CONTRACT_LEGAL
        legal_signals = [
            "master services agreement", "msa", "service level agreement", "sla",
            "data processing agreement", "dpa", "order form", "terms and conditions",
            "terms of service", "indemnification", "limitation of liability", "governing law"
        ]
        for sig in legal_signals:
            if sig in lower_fn:
                scores["CONTRACT_LEGAL"] += 5
            if sig in lower_text:
                scores["CONTRACT_LEGAL"] += 2

        # Pick top scoring category
        best_category = max(scores, key=lambda k: scores[k])
        max_score = scores[best_category]

        if max_score < 3:
            best_category = "GENERAL_RESOURCE"
            confidence = 0.5
        else:
            confidence = min(0.95, 0.5 + (max_score * 0.05))

        # Generate tags
        tags = []
        if detected_competitor:
            tags.append(f"vs {detected_competitor}")
        if detected_industry:
            tags.append(detected_industry)

        for sig in ["SOC2", "GDPR", "HIPAA", "Enterprise", "Pricing", "SLA", "API", "ROI"]:
            if sig.lower() in combined and sig not in tags:
                tags.append(sig)

        # Generate heuristic sales summary
        summary_templates = {
            "BATTLECARD": f"Competitive positioning and rebuttal intelligence against {detected_competitor or 'industry rivals'}.",
            "PRICING_PACKAGING": "Pricing structure, packaging tiers, and discounting guidelines for deal proposals.",
            "CASE_STUDY_ROI": f"Customer proof points and quantified ROI metrics in {detected_industry or 'enterprise environments'}.",
            "SECURITY_COMPLIANCE": "Security posture, compliance certifications, and enterprise trust documentation.",
            "PRODUCT_SPEC": "Detailed technical specifications, architecture blueprints, and product capabilities.",
            "CONTRACT_LEGAL": "Legal contract framework, service level agreements, and commercial commitments.",
            "GENERAL_RESOURCE": f"General business collateral and reference documentation for {filename}."
        }

        return SalesClassificationResult(
            category=best_category,
            target_competitor=detected_competitor,
            target_industry=detected_industry,
            sales_summary=summary_templates.get(best_category, f"Sales collateral: {filename}"),
            sales_tags=tags[:5],
            confidence_score=confidence,
            classifier_used="heuristic_rule_engine",
        )
