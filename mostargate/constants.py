DATA_SIZE = 600
BATCH_SIZE = 20
MODEL = "claude-sonnet-4-5"
COMPANY_POLICY_PATH = "dataset/company_policy.txt"

# 15-permission taxonomy — each maps to a single deployable credential type
TOOLS = {
    "github_read":          "GitHub PAT (read scope) — search codebase, browse code, review PRs",
    "pull_request_create":  "GitHub PAT (write scope) — submit a code change for review",
    "code_execute":         "sandboxed process (no network) — run code, tests, or scripts",
    "confluence_read":      "Confluence API token — search and read internal docs, runbooks, policies",
    "jira_read":            "Jira API token (read) — check ticket status, browse backlog",
    "jira_write":           "Jira API token (write) — create or update tickets, log bugs",
    "slack_read":           "Slack bot token (read history) — read message history, check threads",
    "slack_write":          "Slack bot token (post) — send an internal Slack message",
    "salesforce_read":      "Salesforce API token (read) — CRM data: contracts, renewal dates, contacts",
    "database_read":        "scoped DB credential (read-only) — query PostgreSQL or Snowflake",
    "email_read":           "IMAP/Google Workspace read-scope OAuth — read external email inbox",
    "email_send_external":  "SMTP/SendGrid API key — send email to an external recipient",
    "http_request":         "network egress — outbound HTTP call to an external URL, API, or web search",
    "file_read_uploaded":   "session-scoped buffer — read a file explicitly uploaded by the user",
    "export_file":          "session-scoped output buffer — produce a downloadable output, report, or export",
}

# Tier 1 = Default Deny, Tier 2 = Grant With Justification, Tier 3 = Default Permit
TOOL_TIERS = {
    "database_read":        1,
    "email_send_external":  1,
    "http_request":         1,
    "pull_request_create":  1,
    "github_read":          2,
    "code_execute":         2,
    "slack_read":           2,
    "slack_write":          2,
    "jira_write":           2,
    "salesforce_read":      2,
    "email_read":           2,
    "export_file":          2,
    "confluence_read":      3,
    "jira_read":            3,
    "file_read_uploaded":   3,
}

# Source 1 role-based ceiling — defines C2 experimental condition
DEPARTMENT_CEILINGS = {
    "Engineering": {
        "github_read", "pull_request_create", "code_execute",
        "confluence_read", "jira_read", "jira_write",
        "slack_read", "slack_write", "database_read",
        "http_request", "email_read", "file_read_uploaded", "export_file",
    },
    "Data and Analytics": {
        "confluence_read", "jira_read", "jira_write",
        "slack_read", "slack_write", "database_read",
        "http_request", "email_read", "email_send_external",
        "file_read_uploaded", "export_file",
    },
    "Security": {
        "github_read", "code_execute",
        "confluence_read", "jira_read", "jira_write",
        "slack_read", "slack_write", "database_read",
        "http_request", "email_read", "email_send_external",
        "file_read_uploaded", "export_file",
    },
    "Customer Success": {
        "confluence_read", "jira_read", "jira_write",
        "slack_read", "slack_write", "salesforce_read",
        "database_read", "email_read", "email_send_external",
        "file_read_uploaded", "export_file",
    },
    "Finance": {
        "confluence_read", "jira_read", "jira_write",
        "slack_read", "slack_write",
        "database_read", "email_read", "email_send_external",
        "file_read_uploaded", "export_file",
    },
    "Legal and Compliance": {
        "confluence_read", "jira_read", "jira_write",
        "slack_read", "slack_write",
        "email_read", "email_send_external",
        "file_read_uploaded", "export_file",
    },
}
