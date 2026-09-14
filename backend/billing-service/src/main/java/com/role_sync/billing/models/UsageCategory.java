package com.role_sync.billing.models;

/** What a charge was for, grouped the way the usage page shows it. */
public enum UsageCategory {
	AGENT("AI assistant"),
	SEARCH("Web and knowledge search"),
	DOCUMENTS("Documents"),
	CONNECTORS("Connected apps"),
	CATALOG("Catalog AI"),
	OTHER("Other");

	private final String label;

	UsageCategory(String label) {
		this.label = label;
	}

	public String label() {
		return label;
	}

	/** Unknown or missing categories count as OTHER rather than rejecting a real charge. */
	public static UsageCategory parse(String value) {
		if (value == null || value.isBlank()) {
			return OTHER;
		}
		try {
			return valueOf(value.trim().toUpperCase());
		}
		catch (IllegalArgumentException ex) {
			return OTHER;
		}
	}
}
