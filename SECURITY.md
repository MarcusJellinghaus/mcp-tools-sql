# Security Policy

## Reporting a Vulnerability

Report vulnerabilities through GitHub private vulnerability reporting only: [report a vulnerability](https://github.com/MarcusJellinghaus/mcp-tools-sql/security/advisories/new) (or, in this repository, **Security → Report a vulnerability**).

Do not open public issues for security problems.

## Response

Reports are handled on a best-effort basis. There is no fixed response time.

## Supported Versions

Only the latest release on PyPI receives security fixes.

## Scope

In scope are bypasses of intended restrictions, such as:

- read-only / write-protection of the SQL tools (e.g. executing statements the configuration forbids)
- SQL injection through tool parameters
- credential handling (database credentials and connection configuration leaking into logs, tool output, or error messages)

## Threat Model

Tool arguments and query text supplied by an LLM client are untrusted input. mcp-tools-sql must enforce its configured restrictions regardless of what the client sends. Reports that bypass this are in scope.
