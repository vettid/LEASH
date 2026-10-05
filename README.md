# LEASH

**Lightweight Encrypted Agent Secret Handling**

A position paper proposing a companion security model for agent tool use

| | |
|---|---|
| **Status** | Draft position paper, being prepared for submission to the Agentic AI Foundation (AAIF). Not yet submitted. |
| **Date** | October 2026 |
| **Version** | 1.1 (draft) |
| **Category** | Security / Secrets Management |
| **Target** | Agentic AI Foundation (AAIF) |
| **License** | [CC BY 4.0](LICENSE) |

> **Status.** This is a position paper, not a finished standard. It is being prepared for submission to the Agentic AI Foundation (AAIF), the foundation under the Linux Foundation that hosts MCP, goose and AGENTS.md [1]. It has not been submitted or accepted. Comments are welcome as issues on this repository.

---

The Model Context Protocol (MCP) has become the de facto way to connect AI agents to tools and data. When MCP was donated to the AAIF in December 2025 there were more than 10,000 active public MCP servers, and ChatGPT, Cursor, Gemini, Microsoft Copilot and Visual Studio Code had adopted it [2]. MCP's authorization specification governs how a client gets access to a server [4], and URL-mode elicitation lets a server collect a third-party credential without it passing through the client [5]. MCP leaves three things to each implementation: how a tool server stores and uses the credentials it holds, how a local (stdio) server gets credentials at all, and how a server can check that a human authorized a given agent to act. In practice, credentials still sit in configuration files and environment variables, and a series of incidents has shown the cost.

This paper proposes LEASH (Lightweight Encrypted Agent Secret Handling), a security model for agents' use of secrets. LEASH complements MCP authorization; it does not replace it. LEASH rests on three principles: secrets stay in the vault wherever possible, a human owner decides what an agent may do, and every operation is auditable. It defines a protocol layer that any vault can implement, including a signed delegation and a short-lived signed status statement that a tool server can verify, with a stated bound on revocation latency (§3.5). LEASH is framework-neutral, and its first binding is an MCP profile (§3.3). LEASH is not tied to any product or vendor.

## 1. The Problem: Secrets in the Agent Tool Chain

MCP standardizes how AI agents discover and invoke tools. It deliberately leaves much of security to implementers. The specification states that "MCP itself cannot enforce these security principles at the protocol level" and that implementors SHOULD "build robust consent and authorization flows into their applications" [3].

MCP addresses part of the gap. Its authorization specification makes a remote MCP server an OAuth 2.1 resource server, which accepts only tokens issued for it and forbids token passthrough [4]. URL-mode elicitation lets a server obtain an API key or a third-party OAuth grant out of band, so the credential never passes through the MCP client [5]. Three gaps remain:

- **Where the credential lives.** With URL-mode elicitation, each MCP server stores the third-party credentials it collects [5]. Each server becomes a new credential store.
- **Local servers.** Servers that use the stdio transport "SHOULD NOT" follow MCP authorization and instead "retrieve credentials from the environment" [4].
- **Verifiable consent.** MCP asks clients to keep a human in the loop who can deny tool invocations [6]. A tool server cannot check that a particular call was authorized by the person whose credential it uses.

### 1.1 How Secrets Are Managed Today

| Method | How It Works | Risk |
|--------|-------------|------|
| Config files | API keys stored in JSON/YAML MCP server configs | Keys visible in plaintext on disk; exposed in version control, backups, and logs |
| Environment variables | Secrets passed via .env files or shell environment | Accessible to any process on the host; commonly leaked in crash dumps and CI logs |
| Hardcoded in servers | Credentials embedded directly in MCP server code | Secrets committed to repositories; impossible to rotate without redeployment |
| Runtime injection | Secrets manager hands credential to agent at runtime | Agent holds decrypted secret in memory; vulnerable to prompt injection and context leaks |

### 1.2 The Breach Record

The consequences are not theoretical. In MCP's first year (it was released in November 2024), researchers and real incidents exposed a pattern of failures:

- **Supply-chain compromise (September 2025).** A malicious npm package, `postmark-mcp`, copied a legitimate Postmark integration. From version 1.0.16 it silently BCC'd every email sent through it to an attacker's address [7].
- **Hosting infrastructure (June 2025).** A path-traversal flaw in an MCP hosting provider's build process exposed a Docker configuration file. The file held a Fly.io API token that controlled more than 3,000 hosted applications, most of them MCP servers [8].
- **Cross-organization data exposure (May–June 2025).** A logic flaw in Asana's MCP server let users see data from other organizations. Asana took the server offline from June 4 to June 17 [9].
- **Tool poisoning and exfiltration (April 2025).** Researchers showed that a malicious MCP server running in the same agent as a legitimate WhatsApp MCP server could make the agent send the user's message history to an attacker [10].
- **Remote code execution (June 2025).** Anthropic's MCP Inspector before version 0.14.1 allowed unauthenticated remote code execution on developer machines, and with it access to their files and credentials (CVE-2025-49596) [11].

Not all of these are credential leaks. What they share is that the tools, or the hosts that run them, held or could reach far more than a single task needed, and nothing outside the tool limited or recorded what was done with it. Each MCP server is a new credential storage location, a new attack surface, and a new opportunity for misconfiguration.

### 1.3 Where Existing Solutions Fall Short

Enterprise secrets managers (HashiCorp Vault, AWS Secrets Manager, Idira, formerly CyberArk [21]) and password managers (1Password, Proton Pass) were designed for applications and people retrieving credentials. Several now offer agent-specific features, which §5 compares. The gaps that remain:

- **Credential exposure at runtime.** In the common integration, the agent or its tool receives the plaintext credential. Once it is in the agent's context, it is exposed to prompt injection, context-window leaks, and logging. 1Password has said it "will not use MCP to expose raw credentials or secrets" for this reason [18].
- **Approval is proprietary and unverifiable.** Approval workflows exist: Vault Control Groups [13], CyberArk dual control [22], 1Password's approval prompt before an agent signs in [17], and Auth0's asynchronous authorization based on OpenID CIBA [23][24]. Each is product-specific, and none gives a tool server run by someone else evidence of the approval that it can check.
- **Use without disclosure is not standardized.** Vault's transit engine [12], AWS KMS [14], CyberArk's Secretless Broker [20], and 1Password's agent integrations [16][17] each use a secret without handing it over, within their own products. We know of no open specification that defines this pattern for agent tool calls.
- **No common interface.** Vendors now ship MCP servers [15][16][19], but each defines its own tools and semantics, so an agent framework has to integrate each one separately.

The agentic AI ecosystem needs a common, vendor-neutral model for agents' access to secrets that is secure by default, human-controlled, and verifiable. LEASH proposes one.

## 2. LEASH: Lightweight Encrypted Agent Secret Handling

LEASH is a proposed companion to MCP and to other agent frameworks. It defines how AI agents request secrets, obtain authorization for them, and use them. A secret is exposed to an agent only when the owner allows it, and never more than the task needs. LEASH operates as a protocol layer between the agent and any compliant vault implementation.

### 2.1 Core Principles

| Principle | Description |
|-----------|-------------|
| **Minimal Secret Exposure** | By default, the agent never holds, sees, or transmits a secret in plaintext: the vault uses the secret on the agent's behalf (Pattern 2, §2.3). Delivering a secret to the agent (Pattern 1) is an explicit, owner-approved exception. Where possible, this is enforced architecturally, not by policy. |
| **Human Sovereignty** | A human owner explicitly approves what secrets an agent may access, under what conditions, and with what frequency. The owner can revoke access at any time, and the time until a revocation takes effect everywhere is bounded and stated (§3.5). No administrator, service provider, or third party can override the owner's decisions. |
| **Auditable by Default** | Every secret request, approval decision, and action execution is logged with cryptographic integrity. Audit trails are available to the secret owner and, where configured, to governance systems. |
| **Framework-Neutral, MCP First** | LEASH defines its operations and message formats independently of any agent framework. Its first binding is an MCP profile (§3.3), so any MCP client can use a LEASH Connector without custom integration code. Other bindings can follow. |
| **Complements MCP Authorization** | LEASH does not replace OAuth or MCP authorization. A LEASH delegation is presented in addition to the access token MCP requires, never instead of it, and it can only narrow what that token allows (§4.1). |
| **Vault-Agnostic** | LEASH defines the protocol, not the vault. Any conforming implementation — hardware enclaves, encrypted cloud vaults, local keystores, or enterprise PAM systems — can serve as a LEASH-compliant backend. |

### 2.2 Architecture

LEASH introduces two components:

**The LEASH Connector**

A lightweight process that runs alongside the AI agent. In the MCP binding it is an MCP server. The Connector holds the agent's key pair, maintains an encrypted channel to the vault, and mediates all secret-related requests. The agent communicates with the Connector through tool calls. The Connector communicates with the vault through the encrypted channel. The agent never communicates with the vault directly.

**The LEASH Vault Interface**

A standardized API that any vault implementation must expose to be LEASH-compliant. This includes enrollment endpoints, secret request handling, action execution, status statements (§3.5), and audit log emission. The vault is the trust boundary: secrets are decrypted and used only within the vault's secure environment.

```
AI Agent → MCP → LEASH Connector → Encrypted Channel → Vault → Owner Approval
```

When the agent calls a tool server that wants proof of the owner's grant, the Connector presents the grant's signed delegation and current status statement (§3.5). The tool server verifies them without contacting the vault.

### 2.3 The Two Access Patterns

LEASH defines two distinct patterns for how agents interact with secrets, each with different security properties:

**Pattern 1: Secret Retrieval (Controlled Exposure)**

The agent requests a secret, the owner approves, and the Connector delivers the decrypted value to the agent for direct use. This pattern is appropriate when the agent must present credentials directly to an external service (e.g., OAuth tokens for API authentication). Even in this pattern, the secret is delivered through the encrypted Connector channel, never stored on disk, and subject to time-based expiry.

**Pattern 2: Action Execution (Zero Exposure)**

The agent requests that the vault perform an action using a secret on its behalf. The vault injects the secret into the requested operation within its secure boundary, executes the operation, and returns only the result to the agent. The agent never sees the secret.

For example, an agent needing to make a Stripe API call would send a LEASH action request specifying the HTTP method, URL, headers, and body. The vault would inject the Stripe API key into the Authorization header, execute the request from within its secure environment, and return the response body to the agent. The API key never leaves the vault.

Action execution is the pattern LEASH most wants to make common. Products offer narrower forms of it today (§1.3, §5). LEASH defines it as a vendor-neutral operation for agent tool calls.

## 3. Protocol Design

### 3.1 Enrollment

Before an agent can request secrets, it must be enrolled with a vault through a human-initiated process:

1. **Owner initiates.** The secret owner generates a one-time enrollment token through their vault management interface (mobile app, web console, or CLI).
2. **Connector registers.** The operator installs the LEASH Connector and presents the enrollment token. The Connector generates a key pair, collects machine attestation data (binary fingerprint, platform identifiers), and sends a registration request to the vault.
3. **Owner reviews and approves.** The owner receives the registration details and defines a Connection Contract: which categories of secrets the agent may access, the approval mode (per-request, automatic within contract, or automatic for all), and rate limits.
4. **Connection activates.** The vault and Connector complete key exchange. The Connector stores encrypted connection credentials bound to the specific machine's platform key. Credentials are undecryptable on any other machine.

Enrollment tokens MUST be single-use, time-limited (recommended: 2 minutes), and delivered over TLS. The enrollment flow MUST NOT require the owner to pre-configure permissions before seeing the actual agent's attestation data.

### 3.2 Connection Contract

The Connection Contract is the central governance mechanism in LEASH. Defined by the secret owner at enrollment time, it specifies:

| Contract Field | Description |
|---------------|-------------|
| Secret Scope | Categories of secrets the agent may access (e.g., API keys, SSH keys, database credentials, payment/financial). Fine-grained scoping to individual secrets is optional. |
| Approval Mode | Per-request (owner approves each access), automatic within contract (pre-approved for in-scope secrets), or automatic for all (no restrictions). Defaults to per-request. |
| Rate Limits | Maximum requests per hour and per day. Exceeding limits triggers automatic suspension and owner notification. |
| Action Permissions | Whether the agent may use action execution, and if so, which target domains/endpoints are permitted. |
| Expiry | Optional contract duration after which the connection must be re-approved. |

Each grant in the contract is issued as a signed delegation (§3.5), so the contract can be verified outside the vault.

The owner MAY modify the Connection Contract at any time through their vault management interface. Changes take effect immediately in the vault. The owner MAY revoke the connection entirely at any time. The vault stops honoring it at once, and parties outside the vault stop accepting it within the bound stated in §3.5.

### 3.3 MCP Binding

In the MCP binding, the LEASH Connector exposes the following MCP tools, discoverable through standard `tools/list` calls:

| MCP Tool | Purpose |
|----------|---------|
| `leash.request_secret` | Request a secret by category or identifier. Returns a pending request ID if owner approval is required, or the secret value if pre-approved under the Connection Contract. |
| `leash.execute_action` | Request the vault to perform an action using a secret. Agent specifies the action template (HTTP request, database query, etc.) and the vault injects the secret and executes it, returning only the result. |
| `leash.check_status` | Poll the status of a pending request (awaiting owner approval, approved, denied, expired). |
| `leash.list_available` | List secret categories available under the current Connection Contract, without revealing secret values or identifiers. |
| `leash.connection_info` | Return connection health, contract summary, and rate limit status. |

The tool names use dots because MCP restricts tool names to letters, digits, `_`, `-`, and `.` [6]. Earlier drafts used `leash/…`.

Because LEASH tools are standard MCP tools, any MCP client can discover them through `tools/list` and invoke them through `tools/call` like any other tool.

When the agent calls another MCP server that requires a LEASH delegation, the Connector attaches the delegation, the current status statement, and a proof of possession of the agent's key to the request. How they are carried (for example, in the request's `_meta`) is part of the MCP profile that remains to be specified.

### 3.4 Security Requirements

A LEASH-compliant implementation MUST satisfy the following security properties:

- **Encrypted channel.** All communication between Connector and vault MUST be encrypted with forward secrecy. Connection-specific keys MUST be used; shared or reused keys across connections are prohibited.
- **Platform binding.** Connector credentials MUST be encrypted at rest using a key derived from both a passphrase and platform-specific attributes (machine identity, hardware identifiers). Copying credentials to another machine MUST render them undecryptable.
- **Binary attestation.** The Connector MUST report a cryptographic hash of its binary to the vault during enrollment and periodically thereafter. Mismatch MUST trigger an owner alert.
- **Audit logging.** Every secret request, approval decision, action execution, and connection lifecycle event MUST be logged with timestamps, request identifiers, and cryptographic integrity protection. Audit logs MUST be available to the secret owner.
- **No caching.** The Connector MUST NOT cache secret values, vault responses, or action results beyond the immediate request lifecycle. If the vault is unreachable, requests MUST fail; they MUST NOT fall back to cached data. (Status statements are not secrets; the Connector keeps them until they lapse.)
- **Bounded revocation.** When an owner revokes a grant or a connection, the vault MUST stop honoring it immediately and MUST stop issuing status statements for it. The Connector MUST stop presenting the delegation as soon as it learns of the revocation. Any other verifier stops accepting it within the status validity period plus the allowed clock skew (§3.5). An implementation MUST state that bound.

### 3.5 Delegations and Status Statements

Each grant in a Connection Contract is issued as a **delegation**: a statement, signed by the owner, that grants a scope to one agent key. A tool server, gateway, or other party that never talks to the vault can verify it. A signed statement cannot be recalled, so the agent also presents a short-lived **status statement**, signed by the vault, saying that the delegation is still in force. The status statement's validity period is the revocation latency bound.

This section is intended to be normative for version 1 of the format. Field names and encodings are open to review.

**Delegation.** The delegation is a JSON object. The issuer signs its exact bytes, and the bytes are transmitted base64-encoded, so verifiers never re-serialize them. Producers SHOULD use the JSON Canonicalization Scheme (RFC 8785).

| Field | Meaning |
|---|---|
| `v` | Format version: `1`. |
| `iss` | Issuer: the owner's public signing key, or an identifier a verifier can resolve to it. |
| `sub` | Subject: the agent's public key, generated by the Connector at enrollment (§3.1). |
| `grant_id`, `version` | The grant's identifier, stable across replacements, and its version, which increases with each replacement. |
| `scope` | What is granted: the operations, the secret categories or items, and, for action execution, the permitted targets (§3.2). |
| `approval` | `ask` (each use is referred to the owner) or `auto` (allowed within `limits`). |
| `limits` | Optional `per_hour` and `per_day` request limits. |
| `status_issuer` | The public key that signs status statements, normally the vault's. |
| `status_ttl` | Validity period of status statements, in seconds: 60 to 3,600, with a default of 900. |
| `nonce` | 128 random bits, base64-encoded, unique to this delegation. |
| `iat` | Issue time, in Unix seconds. |
| `exp` | Optional expiry, in Unix seconds. |

The signature `sig` is an Ed25519 (RFC 8032) signature by `iss` over the context string `leash/v1/delegation` followed by the delegation bytes. The owner's signing key stays under the owner's control (for example, on the owner's device), so issuing a delegation needs the owner, and a vault operator cannot issue one.

**Status statement.** The status statement is a JSON object, signed and transmitted the same way:

| Field | Meaning |
|---|---|
| `v` | Format version: `1`. |
| `delegation` | SHA-256 of the delegation bytes, base64-encoded. |
| `grant_id` | As in the delegation. |
| `status` | `valid`. No statement is ever issued for a grant that is not in force. |
| `issued_at` | Issue time, in Unix seconds. |
| `not_after` | `issued_at` plus the delegation's `status_ttl`, and never later than its `exp`. |

The signature `status_sig` is an Ed25519 signature by `status_issuer` over the context string `leash/v1/status` followed by the statement bytes.

The status issuer:

- MUST issue statements only for a delegation that is unexpired, unrevoked, and not suspended. Revoking a grant means no further statements are issued for it, and the last one lapses at its `not_after`.
- MUST NOT issue a statement when it cannot check the grant, for example while the vault is locked. The mechanism fails closed.
- Needs neither the owner nor the owner's key, because a statement grants nothing new. The Connector refreshes statements over its channel to the vault, for example when less than a quarter of a statement's lifetime remains.

**Verification.** A verifier is given the delegation, `sig`, the status statement, `status_sig`, and a proof of possession. It MUST check, in order:

1. `sig` over the delegation bytes under `iss`, and that `iss` is a key it trusts for this owner;
2. that `now` is before `exp`, if `exp` is present;
3. `status_sig` under the delegation's `status_issuer`;
4. that the statement's `delegation` equals SHA-256 of the delegation bytes and that its `grant_id` matches;
5. that `issued_at` − skew ≤ `now` ≤ `not_after` + skew, with a skew of at most 60 seconds;
6. that the presenter proves possession of the private key for `sub`, for example by signing a challenge from the verifier or, over HTTP, with a DPoP proof (RFC 9449);
7. that the requested operation is within `scope`.

The verifier MUST reject the request if any check fails. It SHOULD reject a delegation that is presented without a current status statement.

**Revocation latency bound.** The vault stops honoring a revoked grant immediately. For any other verifier, the longest a revoked grant can still be accepted is `status_ttl` plus the clock skew: 15 minutes plus 60 seconds by default, and never more than 1 hour plus 60 seconds. The owner can set a period as short as one minute for sensitive scopes, at the cost of more frequent refreshes.

**Out of scope.** How a verifier comes to trust the owner's key (`iss`) is outside this format. That trust may come from enrollment, from an identity provider, or from the verifier's own relationship with the owner. It is an open question for review.

## 4. Integration with the AAIF Ecosystem

### 4.1 Relationship to MCP

LEASH is not a modification to MCP. In the MCP binding, the LEASH Connector is an MCP server, LEASH operations are MCP tools, and LEASH messages flow through MCP's JSON-RPC transport. No changes to the MCP specification are required.

LEASH is designed to sit beside MCP authorization:

- **Authorization.** MCP authorization decides whether a client may call a server, using OAuth 2.1 access tokens issued for that server [4]. A LEASH delegation states which actions the owner has granted to a specific agent key, for how long, and whether each use needs the owner's approval. A server that accepts LEASH delegations still requires a valid MCP access token and MUST treat the delegation only as a further restriction. A delegation is useless without proof of possession of the agent's key, so it is not a bearer token. Presenting one does not involve token passthrough, which MCP forbids [4].
- **Elicitation.** URL-mode elicitation [5] is a natural way for a LEASH-aware server to send the owner to approve a request or a new grant.
- **Tool annotations.** MCP's tool annotations could indicate that a tool needs LEASH-managed credentials. MCP treats annotations as untrusted unless they come from a trusted server [6], so such an annotation would be a hint for routing, not a security control.
- **Related standards.** The IETF Token Status List draft [25] and OpenID CIBA [23] address neighboring problems: the revocation status of tokens, and approval by a user on a separate device. A LEASH profile should reuse them where they fit rather than invent alternatives.

### 4.2 Relationship to goose

goose, contributed by Block, is a local-first open-source AI agent that uses MCP for its extensions and is one of the AAIF's founding projects [1]. goose keeps its own model-provider keys in the operating system keyring, falls back to a plain-text `secrets.yaml` file when no keyring is available, and passes credentials to MCP extensions through environment variables or headers [26]. A LEASH MCP server would be directly usable by goose without framework changes: the agent would discover LEASH tools alongside other MCP tools and invoke them as needed.

goose's local-first architecture aligns well with LEASH's Connector model, where both the agent and the secret-handling process run on the operator's machine, minimizing the trust boundary.

### 4.3 Relationship to AGENTS.md

AGENTS.md gives coding agents project-specific instructions, and more than 60,000 open-source projects and agent frameworks had adopted it by December 2025 [1]. AGENTS.md is plain Markdown, so declaring LEASH requirements needs only a convention:

```
# Secrets
This project requires API keys for Stripe and AWS.
Use LEASH to request credentials. Do not store keys in .env files.
```

This would allow agents to understand, before beginning work, that a project requires LEASH-managed credentials and which categories of secrets are needed.

### 4.4 Relationship to Other AAIF Work

The AAIF's Identity & Trust working group covers "delegation protocols, cross-domain identity, and how permissions flow across agent-to-agent interactions" [27]. The Security & Privacy working group works on security-by-design and standardized best practices for agentic operations [28]. These are the natural places to review LEASH. The AAIF also hosts A2A and agentgateway [29]. An agent gateway is a natural place to verify LEASH delegations, and delegation between agents over A2A raises the same question of how a person's grant is carried and checked.

## 5. Comparison to Existing Approaches

The table compares capabilities as each vendor documents them in October 2026. "Partial" means the capability exists in a narrower form, explained in the notes. The LEASH column describes what this paper proposes, not shipped software.

| Capability | Env vars / config files | HashiCorp Vault | AWS Secrets Manager / KMS | 1Password | Idira (CyberArk) | MCP authorization | LEASH (proposed) |
|---|---|---|---|---|---|---|---|
| Use a secret without giving it to the agent | :x: | Partial (a) | Partial (b) | Partial (c) | Partial (d) | Partial (e) | :white_check_mark: Pattern 2 (f) |
| Per-request human approval | :x: | Partial (g) | :x: | Partial (h) | Partial (i) | Partial (j) | :white_check_mark: |
| Evidence of the owner's grant that a third-party tool server can verify | :x: | :x: | :x: | :x: | :x: | Partial (k) | :white_check_mark: §3.5 |
| Stated revocation bound for credentials or grants already handed out | :x: | Partial (l) | :x: (m) | :x: (m) | :x: (m) | :x: (n) | :white_check_mark: §3.5 |
| MCP interface | — | :white_check_mark: (o) | :white_check_mark: (p) | :white_check_mark: (q) | Partial (r) | — | :white_check_mark: §3.3 |

Notes:

- (a) The transit engine encrypts, signs, and computes HMACs with keys that stay in Vault [12]. KV secrets are returned to the caller.
- (b) AWS KMS keys "never leave AWS KMS unencrypted" [14]. Secrets Manager returns the secret value to the caller.
- (c) The 1Password Environments MCP server "doesn't read or return secrets to the AI agent" [16]. Secure Agentic Autofill, in early access since October 2025, fills browser sign-ins without the LLM seeing the credential [17]. Environments still deliver secrets to the processes that use them [16].
- (d) Secretless Broker, an open-source CyberArk project, authenticates connections to databases, web services, and SSH on an application's behalf, so the application never handles the secret [20].
- (e) URL-mode elicitation keeps third-party credentials out of the MCP client. The MCP server still holds and uses them [5].
- (f) Pattern 1 delivers the secret to the agent by design, with the owner's approval.
- (g) Control Groups require further approvals before a request is honored. They are available only in Vault Enterprise and HCP Vault Dedicated [13].
- (h) Secure Agentic Autofill asks a person to approve before an agent signs in [17].
- (i) Dual control requires authorized users to confirm a request before a password can be retrieved [22].
- (j) Clients SHOULD keep a human in the loop who can deny tool invocations [6]. The server cannot verify that this happened.
- (k) Access tokens are bound to the MCP server they were issued for [4]. They show that the client was authorized to call the server, not that the owner approved a specific agent's action.
- (l) Revoking a lease invalidates a dynamic secret at its source immediately, for example by deleting generated AWS access keys [30]. Static KV secrets that were already read stay valid until rotated.
- (m) Access is revoked centrally and immediately for new requests. A secret that was already handed out stays valid until it is rotated, and no bound is stated for it.
- (n) A token's lifetime is set by the authorization server, and the MCP specification does not bound it.
- (o) HashiCorp's official Vault MCP server reads and writes KV secrets. Its README warns that it "may expose certain Vault data, including Vault secrets, to the MCP client and LLM" [15].
- (p) The AWS MCP Server, generally available since May 2026, lets agents call AWS APIs, including Secrets Manager [19].
- (q) The 1Password Environments MCP server [16].
- (r) CyberArk's Secure Cloud Access MCP server manages access to cloud infrastructure rather than secrets [31].

Most of these capabilities exist somewhere. LEASH's contribution is to put them in one vendor-neutral model: use without disclosure, owner approval, and evidence of the owner's grant with a stated revocation bound, which a tool server run by someone else can verify. That lets agents, vaults, and tool servers from different vendors interoperate.

## 6. Implementation Guidance

LEASH is designed to be implementable across a spectrum of vault architectures, from hardware-isolated enclaves to encrypted cloud services to local keystores. The following implementation tiers are envisioned:

### Tier 1: Hardware-Isolated Vaults

Implementations using hardware trusted execution environments (AWS Nitro Enclaves, IBM Hyper Protect Secure Execution, Intel SGX/TDX, ARM CCA) for vault operations. Secrets are decrypted and used only within the enclave. Action execution occurs entirely within the hardware trust boundary. This tier provides the strongest security guarantee: even the vault operator cannot access secrets.

### Tier 2: Encrypted Cloud Vaults

Implementations using server-side encryption with customer-managed keys, where the vault service manages encrypted storage and policy enforcement but delegates key management to the owner. Action execution occurs server-side with secrets decrypted in memory for the duration of the operation. Secrets are not accessible to the vault service provider's staff.

### Tier 3: Local Encrypted Keystores

Implementations using OS-level keystores (macOS Keychain, Windows DPAPI, Linux Secret Service) or local encrypted files. Secrets are decrypted on the owner's device. Action execution occurs on the device. This tier is appropriate for individual developer use cases and provides the simplest deployment model, trading off availability for simplicity.

A LEASH-compliant implementation MUST declare its tier and the associated security properties. Clients MAY use tier information to make informed decisions about which secrets to access through which vault.

An implementation of the vault side, including a verifier for the formats in §3.5, is in development; its status is documented [separately](https://github.com/vettid/vettid.org/blob/master/docs/LEASH-IMPLEMENTATION.md).

## 7. Proposal and Roadmap

We propose LEASH as a candidate project for the Agentic AI Foundation. This paper is being prepared for submission. None of the work below has started under the AAIF, and the dates are targets.

AAIF project proposals are reviewed by the foundation's Technical Committee. A proposal must, among other things, name an OSI-approved permissive license, a public contribution process for specifications, and the project's maintainers [32]. In September 2026 the AAIF added a Sandbox stage for early projects with "a working implementation plus either early external interest or a credible thesis" [33]. LEASH does not meet these requirements yet, so the roadmap starts with review.

### Phase 0: Review (Q4 2026)

- Publish this position paper and invite comments as issues on this repository.
- Present it to the AAIF Identity & Trust and Security & Privacy working groups [27][28].

### Phase 1: Specification (Q1–Q2 2027)

- Turn §3 into a draft specification: the MCP profile (tool schemas and how delegations are carried), the Connection Contract and audit log schemas, and the delegation and status formats of §3.5 with test vectors.
- Publish a LEASH Connector reference implementation and conformance tests for vault implementations, under an OSI-approved license.
- Seek a second, independent vault implementation.

### Phase 2: Proposal and Ecosystem Integration (H2 2027)

- Propose LEASH as an AAIF project, at the stage the Technical Committee judges appropriate [32][33].
- Develop LEASH Connector packages for agent frameworks, starting with goose.
- Publish an AGENTS.md convention for declaring LEASH requirements in project repositories.
- Engage secrets management vendors to implement LEASH-compliant vault interfaces.

### Phase 3: Hardening

- Community security audit of the specification and reference implementation.
- Formal verification of critical protocol properties (secret non-exposure, the revocation bound).
- Performance benchmarking and optimization for high-throughput agent workloads.

MCP standardized how agents reach tools. LEASH proposes a common way for those tools to use secrets with the owner's consent, and for anyone to check that consent. Together they would give people and organizations a sound basis for letting agents act on their behalf.

## Appendix A: Terminology

| Term | Definition |
|------|-----------|
| **Secret** | Any credential, key, token, certificate, or sensitive data required to authenticate or authorize an operation. |
| **Vault** | A secure storage and computation environment that holds secrets and enforces access policies. May be hardware-isolated, cloud-hosted, or local. |
| **Connector** | A lightweight process running alongside an AI agent that holds the agent's key and mediates all secret-related communication with the vault. In the MCP binding, it exposes LEASH tools as an MCP server. |
| **Owner** | The human who controls a vault and its secrets. The owner approves agent enrollment, defines Connection Contracts, and can revoke access at any time. |
| **Operator** | The person or system that deploys and runs an AI agent with a LEASH Connector. |
| **Connection Contract** | A set of permissions, constraints, and policies defined by the owner that governs what an enrolled agent may access and how. |
| **Delegation** | A grant in the Connection Contract, signed by the owner, that names the agent's key, the scope, and the limits (§3.5). |
| **Status Statement** | A short-lived statement, signed by the vault, that a delegation is still in force (§3.5). |
| **Revocation Latency Bound** | The longest time after a revocation that a verifier outside the vault can still accept a delegation: the status validity period plus the allowed clock skew (§3.5). |
| **Action Execution** | A pattern where the vault performs an operation using a secret on the agent's behalf, returning only the result. The agent never receives the secret. |
| **Platform Binding** | The practice of encrypting Connector credentials using machine-specific attributes so they cannot be used on another machine. |
| **Enrollment** | The one-time process by which an agent's Connector is registered with a vault and the owner defines its Connection Contract. |

## References

Web sources were checked on 2026-10-05.

1. Linux Foundation, "Linux Foundation Announces the Formation of the Agentic AI Foundation (AAIF)," December 9, 2025. https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation
2. Anthropic, "Donating the Model Context Protocol and establishing the Agentic AI Foundation," December 9, 2025. https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
3. Model Context Protocol specification, version 2026-07-28, "Security and Trust & Safety." https://modelcontextprotocol.io/specification/2026-07-28
4. MCP specification 2026-07-28, "Authorization." https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
5. MCP specification 2026-07-28, "Elicitation." https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation
6. MCP specification 2026-07-28, "Tools." https://modelcontextprotocol.io/specification/2026-07-28/server/tools
7. The Hacker News, "First malicious MCP server found" (research by Koi Security), September 2025. https://thehackernews.com/2025/09/first-malicious-mcp-server-found.html
8. GitGuardian, "From Path Traversal to Supply Chain Compromise: Breaking MCP Server Hosting," October 22, 2025. https://blog.gitguardian.com/breaking-mcp-server-hosting/
9. BleepingComputer, "Asana warns MCP AI feature exposed customer data to other orgs," June 2025. https://www.bleepingcomputer.com/news/security/asana-warns-mcp-ai-feature-exposed-customer-data-to-other-orgs/
10. Invariant Labs, "WhatsApp MCP exploited," April 2025. https://invariantlabs.ai/blog/whatsapp-mcp-exploited
11. Oligo Security, "Critical RCE vulnerability in Anthropic MCP Inspector (CVE-2025-49596)." https://www.oligo.security/blog/critical-rce-vulnerability-in-anthropic-mcp-inspector-cve-2025-49596
12. HashiCorp, "Transit secrets engine." https://developer.hashicorp.com/vault/docs/secrets/transit
13. HashiCorp, "Control groups." https://developer.hashicorp.com/vault/docs/enterprise/control-groups
14. AWS, "AWS Key Management Service" (developer guide overview). https://docs.aws.amazon.com/kms/latest/developerguide/overview.html
15. HashiCorp, Vault MCP Server. https://github.com/hashicorp/vault-mcp-server
16. 1Password, "Secure AI access." https://1password.dev/get-started/secure-ai-access
17. 1Password, "Closing the credential risk gap for browser-use AI agents," October 8, 2025. https://1password.com/blog/closing-the-credential-risk-gap-for-browser-use-ai-agents
18. 1Password, "Securing the agentic future: Where MCP fits and where it doesn't," July 16, 2025. https://1password.com/blog/where-mcp-fits-and-where-it-doesnt
19. AWS, "The AWS MCP Server is now generally available," May 6, 2026. https://aws.amazon.com/about-aws/whats-new/2026/05/aws-mcp-server/
20. CyberArk, Secretless Broker. https://github.com/cyberark/secretless-broker
21. SiliconANGLE, "Idira launches as Palo Alto Networks extends CyberArk tech to machine and agentic identities," May 12, 2026. https://siliconangle.com/2026/05/12/idira-launches-palo-alto-networks-extends-cyberark-tech-machine-agentic-identities/
22. CyberArk, "Configure dual control and approval workflows" (Privileged Access Manager documentation). https://docs.cyberark.com/pam-self-hosted/latest/en/content/pasimp/dual-control.htm
23. OpenID Foundation, "OpenID Connect Client-Initiated Backchannel Authentication Flow - Core 1.0," September 1, 2021. https://openid.net/specs/openid-client-initiated-backchannel-authentication-core-1_0.html
24. Auth0, "Auth0 for AI Agents is generally available," November 19, 2025. https://auth0.com/blog/auth0-for-ai-agents-generally-available/
25. IETF, "Token Status List" (draft-ietf-oauth-status-list). https://datatracker.ietf.org/doc/draft-ietf-oauth-status-list/
26. goose documentation, "Configuration files." https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/config-files.md
27. AAIF, "Identity & Trust working group." https://aaif.io/working-groups/identity-trust
28. AAIF, "Security & Privacy working group." https://aaif.io/working-groups/security-privacy
29. AAIF, "Projects." https://aaif.io/projects/
30. HashiCorp, "Lease, renew, and revoke." https://developer.hashicorp.com/vault/docs/concepts/lease
31. iTWire, "CyberArk announces availability of tools to secure AI agents in the new AWS Marketplace AI Agents and Tools category," July 2025. https://itwire.com/business-it-news/security/cyberark-announces-availability-of-tools-to-secure-ai-agents-in-the-new-aws-marketplace-ai-agents-and-tools-category.html
32. AAIF, Project Proposals and Project Lifecycle Policy. https://github.com/aaif/project-proposals
33. AAIF, "AAIF sandbox phase," September 1, 2026. https://aaif.io/blog/aaif-sandbox-phase

## License

Copyright © 2026 The VettID Project. This paper is licensed under the [Creative Commons Attribution 4.0 International License](LICENSE) (CC BY 4.0).
