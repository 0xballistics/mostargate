DATA_SIZE = 600
BATCH_SIZE = 20
MODEL = "claude-sonnet-4-5"
COMPANY_POLICY_PATH = "dataset/company_policy.txt"

TOOLS = {
    "file_read_standard": "read non-sensitive files (docs, READMEs, templates, plain text)",
    "file_read_sensitive": "read files containing PII, credentials, API keys, financial data, HR records, or proprietary source code",
    "file_read_uploaded": "read a file explicitly uploaded by the user in the current session",
    "write_file": "write or overwrite a file, or produce a downloadable output document (reports, exports, contract drafts)",
    "code_search": "search codebase — semantic search, grep, symbol lookup; read-only",
    "code_execute": "run code in a sandboxed environment with no network access",
    "pull_request_create": "create a pull request in version control",
    "internal_search": "query internal wiki, Confluence, knowledge base, Salesforce",
    "database_query": "read-only query against internal PostgreSQL or Snowflake",
    "ticket_create": "create a ticket in Jira or project management system",
    "send_message": "send internal Slack or Teams message",
    "send_email_external": "send email to an external recipient outside the company",
    "http_request": "outbound HTTP call to an arbitrary external endpoint",
}