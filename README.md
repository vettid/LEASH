# LEASH

**Lightweight Encrypted Agent Secret Handling**

A Proposed Standard for the Agentic AI Foundation — Position Paper

| | |
|---|---|
| **Status** | Initial Submission |
| **Date** | February 2026 |
| **Version** | 1.0 |
| **Category** | Security / Secrets Management |
| **Target** | AAIF Technical Steering |

---

The Model Context Protocol (MCP) has become the universal standard for connecting AI agents to external tools and data, with over 10,000 published servers and adoption across every major AI platform. Yet MCP has no native mechanism for secure secret management. Credentials are stored in configuration files, injected through environment variables, or hardcoded into server implementations. The result is a growing catalog of real-world breaches: credential leaks, supply-chain compromises, and data exfiltration through the very infrastructure designed to make agents useful.

This paper proposes LEASH (Lightweight Encrypted Agent Secret Handling), a companion standard to MCP that provides a secure, auditable, human-controlled mechanism for AI agents to access secrets. LEASH is built on three principles: secrets never leave the vault, humans approve every access, and every operation is auditable. Rather than replacing existing secrets managers, LEASH defines a protocol layer that any vault implementation can adopt, ensuring interoperability across the agentic AI ecosystem.

## 1. The Problem: MCP Has a Secrets Gap

MCP standardizes how AI agents discover and invoke tools. It does not standardize how those tools obtain the credentials they need to function. This is by design: the MCP specification states that it "cannot enforce these security principles at the protocol level" and that implementors "SHOULD build robust consent and authorization flows into their applications."

In practice, this means every MCP server implements credential handling independently, with predictable results.

### 1.1 How Secrets Are Managed Today

| Method | How It Works | Risk |
|--------|-------------|------|
| Config files | API keys stored in JSON/YAML MCP server configs | Keys visible in plaintext on disk; exposed in version control, backups, and logs |
| Environment variables | Secrets passed via .env files or shell environment | Accessible to any process on the host; commonly leaked in crash dumps and CI logs |
| Hardcoded in servers | Credentials embedded directly in MCP server code | Secrets committed to repositories; impossible to rotate without redeployment |
| Runtime injection | Secrets manager hands credential to agent at runtime | Agent holds decrypted secret in memory; vulnerable to prompt injection and context leaks |

### 1.2 The Breach Record

The consequences are not theoretical. In the first year of MCP adoption, security researchers and real-world incidents have exposed a pattern of credential-related failures:

- **Supply-chain compromise:** A malicious MCP server package masquerading as a legitimate Postmark integration silently BCC'd all email traffic, including confidential documents, to an attacker-controlled server.
- **Hosting infrastructure breach:** A Docker configuration leak from an MCP hosting provider exposed a Fly.io API token granting control over 3,000+ applications, turning the hosting service into a supply-chain attack vector.
- **Cross-organization data exposure:** A flaw in Asana's MCP server implementation allowed users to view other organizations' data, requiring two weeks of downtime to remediate.
- **Tool poisoning and exfiltration:** Researchers demonstrated that a malicious MCP server could silently exfiltrate a user's entire WhatsApp history by combining tool poisoning with a legitimate server in the same agent session.
- **Remote code execution:** Anthropic's own MCP Inspector tool was found to allow unauthenticated remote code execution, exposing the entire filesystem, API keys, and environment secrets on developer workstations.

These incidents share a common root cause: secrets are stored and transmitted without a standardized security layer. Each MCP server is a new credential storage location, a new attack surface, and a new opportunity for misconfiguration.

### 1.3 Why Existing Solutions Fall Short

Enterprise secrets managers (HashiCorp Vault, AWS Secrets Manager, CyberArk) and consumer password managers (1Password, Proton Pass) were designed for human-initiated credential retrieval. They solve the storage problem but not the agent access problem. Specifically:

- **Credential exposure at runtime.** Even when secrets are retrieved securely from a vault, the agent ultimately receives the plaintext credential. Once in the agent's context, it is vulnerable to prompt injection, context window leaks, and logging.
- **No per-request human approval.** Existing managers authenticate applications, not individual operations. An agent with a valid service account token can access any secret in its scope without per-request oversight.
- **No action execution pattern.** No existing solution allows a vault to execute an action using a secret on the agent's behalf, returning only the result. The agent must always receive the credential to use it.
- **No MCP-native integration.** None of these tools define an MCP-compatible interface. Integration requires custom code in every MCP server, which is the exact pattern that produced the current breach landscape.

The agentic AI ecosystem needs a standardized protocol for secret access that is secure by default, human-controlled, and native to MCP. That protocol is LEASH.

## 2. LEASH: Lightweight Encrypted Agent Secret Handling

LEASH is a proposed companion standard to MCP that defines how AI agents request, receive authorization for, and use secrets without those secrets ever being exposed to the agent or its runtime environment. LEASH operates as a protocol layer between the agent and any compliant vault implementation.

### 2.1 Core Principles

| Principle | Description |
|-----------|-------------|
| **Zero Secret Exposure** | The agent never holds, sees, or transmits a secret in plaintext. Secrets remain within the vault's trust boundary at all times. This is enforced architecturally, not by policy. |
| **Human Sovereignty** | A human owner explicitly approves what secrets an agent may access, under what conditions, and with what frequency. The owner can revoke access instantly. No administrator, service provider, or third party can override the owner's decisions. |
| **Auditable by Default** | Every secret request, approval decision, and action execution is logged with cryptographic integrity. Audit trails are available to the secret owner and, where configured, to governance systems. |
| **MCP-Native** | LEASH defines its interface as an MCP server, making it discoverable and invocable through standard MCP client libraries. Any MCP-connected agent can use LEASH without custom integration code. |
| **Vault-Agnostic** | LEASH defines the protocol, not the vault. Any conforming implementation — hardware enclaves, encrypted cloud vaults, local keystores, or enterprise PAM systems — can serve as a LEASH-compliant backend. |

### 2.2 Architecture

LEASH introduces two components into the MCP ecosystem:

**The LEASH Connector**

A lightweight process that runs alongside the AI agent and exposes a standard MCP server interface. The Connector handles cryptographic operations, maintains an encrypted channel to the vault, and mediates all secret-related requests. The agent communicates with the Connector through standard MCP tool calls. The Connector communicates with the vault through an encrypted channel. The agent never communicates with the vault directly.

**The LEASH Vault Interface**

A standardized API that any vault implementation must expose to be LEASH-compliant. This includes enrollment endpoints, secret request handling, action execution, and audit log emission. The vault is the trust boundary: secrets are decrypted and used only within the vault's secure environment.

```
AI Agent → MCP → LEASH Connector → Encrypted Channel → Vault → Owner Approval
```

### 2.3 The Two Access Patterns

LEASH defines two distinct patterns for how agents interact with secrets, each with different security properties:

**Pattern 1: Secret Retrieval (Controlled Exposure)**

The agent requests a secret, the owner approves, and the Connector delivers the decrypted value to the agent for direct use. This pattern is appropriate when the agent must present credentials directly to an external service (e.g., OAuth tokens for API authentication). Even in this pattern, the secret is delivered through the encrypted Connector channel, never stored on disk, and subject to time-based expiry.

**Pattern 2: Action Execution (Zero Exposure)**

The agent requests that the vault perform an action using a secret on its behalf. The vault injects the secret into the requested operation within its secure boundary, executes the operation, and returns only the result to the agent. The agent never sees the secret.

For example, an agent needing to make a Stripe API call would send a LEASH action request specifying the HTTP method, URL, headers, and body. The vault would inject the Stripe API key into the Authorization header, execute the request from within its secure environment, and return the response body to the agent. The API key never leaves the vault.

Action execution is the architectural innovation that distinguishes LEASH from all existing secrets management approaches. No current standard offers this pattern.

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

The owner MAY modify the Connection Contract at any time through their vault management interface. Changes take effect immediately. The owner MAY revoke the connection entirely at any time, which immediately invalidates the Connector's credentials.

### 3.3 MCP Tool Interface

The LEASH Connector exposes the following MCP tools, discoverable through standard `tools/list` calls:

| MCP Tool | Purpose |
|----------|---------|
| `leash/request_secret` | Request a secret by category or identifier. Returns a pending request ID if owner approval is required, or the secret value if pre-approved under the Connection Contract. |
| `leash/execute_action` | Request the vault to perform an action using a secret. Agent specifies the action template (HTTP request, database query, etc.) and the vault injects the secret and executes it, returning only the result. |
| `leash/check_status` | Poll the status of a pending request (awaiting owner approval, approved, denied, expired). |
| `leash/list_available` | List secret categories available under the current Connection Contract, without revealing secret values or identifiers. |
| `leash/connection_info` | Return connection health, contract summary, and rate limit status. |

Because LEASH tools are standard MCP tools, any MCP client (Claude, ChatGPT, Cursor, Gemini, Copilot, Goose, or custom agents) can use them without modification. The agent simply discovers LEASH tools through `tools/list` and invokes them through `tools/call` like any other MCP tool.

### 3.4 Security Requirements

A LEASH-compliant implementation MUST satisfy the following security properties:

- **Encrypted channel.** All communication between Connector and vault MUST be encrypted with forward secrecy. Connection-specific keys MUST be used; shared or reused keys across connections are prohibited.
- **Platform binding.** Connector credentials MUST be encrypted at rest using a key derived from both a passphrase and platform-specific attributes (machine identity, hardware identifiers). Copying credentials to another machine MUST render them undecryptable.
- **Binary attestation.** The Connector MUST report a cryptographic hash of its binary to the vault during enrollment and periodically thereafter. Mismatch MUST trigger an owner alert.
- **Audit logging.** Every secret request, approval decision, action execution, and connection lifecycle event MUST be logged with timestamps, request identifiers, and cryptographic integrity protection. Audit logs MUST be available to the secret owner.
- **No caching.** The Connector MUST NOT cache secret values, vault responses, or action results beyond the immediate request lifecycle. If the vault is unreachable, requests MUST fail; they MUST NOT fall back to cached data.
- **Instant revocation.** When an owner revokes a connection, the vault MUST immediately invalidate all associated keys. The Connector MUST cease serving requests within one heartbeat interval.

## 4. Integration with the AAIF Ecosystem

### 4.1 Relationship to MCP

LEASH is not a modification to MCP. It is a companion standard that operates within MCP's existing architecture. The LEASH Connector is an MCP server. LEASH tools are MCP tools. LEASH messages flow through MCP's JSON-RPC transport. No changes to the MCP specification are required.

However, LEASH benefits from and could inform two areas of MCP evolution:

- **Authorization flows.** MCP's recent OAuth 2.0 integration provides authentication between clients and servers. LEASH extends this to human-in-the-loop authorization for specific operations, a pattern MCP currently lacks.
- **Tool annotations.** MCP's tool annotation system could be extended to indicate that a tool requires LEASH-managed credentials, enabling clients to discover and route secret-dependent operations appropriately.

### 4.2 Relationship to Goose

Goose, Block's open-source agent framework, is a local-first AI agent that uses MCP for integrations. Goose agents today manage credentials through environment variables and configuration files. A LEASH MCP server would be directly usable by Goose agents without framework changes: the agent would discover LEASH tools alongside other MCP tools and invoke them as needed.

Goose's local-first architecture aligns well with LEASH's Connector model, where both the agent framework and the secret handling process run on the operator's machine, minimizing the trust boundary.

### 4.3 Relationship to AGENTS.md

AGENTS.md provides project-specific instructions to AI coding agents. A natural extension would be to declare LEASH requirements in AGENTS.md files:

```
# Secrets
This project requires API keys for Stripe and AWS.
Use LEASH to request credentials. Do not store keys in .env files.
```

This would allow agents to understand, before beginning work, that a project requires LEASH-managed credentials and which categories of secrets are needed.

## 5. Comparison to Existing Approaches

| Capability | Env Vars | HashiCorp Vault | AWS SM | 1Password SDK | CyberArk | LEASH |
|-----------|----------|----------------|--------|--------------|----------|-------|
| Agent never sees secret | :x: | :x: | :x: | :x: | :x: | :white_check_mark: |
| Per-request human approval | :x: | :x: | :x: | :x: | :x: | :white_check_mark: |
| Action execution pattern | :x: | :x: | :x: | :x: | :x: | :white_check_mark: |
| MCP-native interface | :x: | :x: | :x: | :x: | :x: | :white_check_mark: |
| Platform-bound credentials | :x: | :x: | :x: | :x: | :white_check_mark: | :white_check_mark: |
| Owner-controlled contracts | :x: | :x: | :x: | Partial | :white_check_mark: | :white_check_mark: |
| Instant revocation | :x: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Three-layer audit trail | :x: | :x: | :x: | :x: | Partial | :white_check_mark: |
| No caching / zero storage | :x: | :x: | :x: | :x: | :x: | :white_check_mark: |

The critical differentiator is the action execution pattern. Every existing approach ultimately delivers the plaintext secret to the requesting application. LEASH's action execution enables a fundamentally different security model where the secret is used but never exposed. This eliminates the entire class of vulnerabilities associated with secrets in agent memory, context windows, and logs.

## 6. Implementation Guidance

LEASH is designed to be implementable across a spectrum of vault architectures, from hardware-isolated enclaves to encrypted cloud services to local keystores. The following implementation tiers are envisioned:

### Tier 1: Hardware-Isolated Vaults

Implementations using hardware trusted execution environments (AWS Nitro Enclaves, IBM Hyper Protect Secure Execution, Intel SGX/TDX, ARM CCA) for vault operations. Secrets are decrypted and used only within the enclave. Action execution occurs entirely within the hardware trust boundary. This tier provides the strongest security guarantee: even the vault operator cannot access secrets.

### Tier 2: Encrypted Cloud Vaults

Implementations using server-side encryption with customer-managed keys, where the vault service manages encrypted storage and policy enforcement but delegates key management to the owner. Action execution occurs server-side with secrets decrypted in memory for the duration of the operation. Secrets are not accessible to the vault service provider's staff.

### Tier 3: Local Encrypted Keystores

Implementations using OS-level keystores (macOS Keychain, Windows DPAPI, Linux Secret Service) or local encrypted files. Secrets are decrypted on the owner's device. Action execution occurs on the device. This tier is appropriate for individual developer use cases and provides the simplest deployment model, trading off availability for simplicity.

A LEASH-compliant implementation MUST declare its tier and the associated security properties. Clients MAY use tier information to make informed decisions about which secrets to access through which vault.

## 7. Proposal for AAIF

We propose that LEASH be adopted as a project within the Agentic AI Foundation with the following roadmap:

### Phase 1: Specification (Q2 2026)

- Formalize the LEASH protocol specification, including MCP tool schemas, enrollment flow, Connection Contract format, and audit log schema.
- Publish a LEASH Connector reference implementation as open-source software under the AAIF.
- Define conformance tests for vault implementations claiming LEASH compliance.

### Phase 2: Ecosystem Integration (Q3 2026)

- Develop LEASH Connector packages for major agent frameworks (Goose, LangChain, CrewAI, AutoGen).
- Publish an AGENTS.md extension for declaring LEASH requirements in project repositories.
- Engage enterprise secrets management vendors to implement LEASH-compliant vault interfaces.

### Phase 3: Hardening (Q4 2026)

- Community security audit of the specification and reference implementation.
- Formal verification of critical protocol properties (secret non-exposure, revocation completeness).
- Performance benchmarking and optimization for high-throughput agent workloads.

The agentic AI ecosystem is moving from experimentation to production. MCP solved the tool integration problem. LEASH solves the secrets problem. Together, they provide the secure, standardized infrastructure that enterprises need to deploy AI agents with confidence.

## Appendix A: Terminology

| Term | Definition |
|------|-----------|
| **Secret** | Any credential, key, token, certificate, or sensitive data required to authenticate or authorize an operation. |
| **Vault** | A secure storage and computation environment that holds secrets and enforces access policies. May be hardware-isolated, cloud-hosted, or local. |
| **Connector** | A lightweight process running alongside an AI agent that exposes LEASH tools as an MCP server and mediates all secret-related communication with the vault. |
| **Owner** | The human who controls a vault and its secrets. The owner approves agent enrollment, defines Connection Contracts, and can revoke access at any time. |
| **Operator** | The person or system that deploys and runs an AI agent with a LEASH Connector. |
| **Connection Contract** | A set of permissions, constraints, and policies defined by the owner that governs what an enrolled agent may access and how. |
| **Action Execution** | A pattern where the vault performs an operation using a secret on the agent's behalf, returning only the result. The agent never receives the secret. |
| **Platform Binding** | The practice of encrypting Connector credentials using machine-specific attributes so they cannot be used on another machine. |
| **Enrollment** | The one-time process by which an agent's Connector is registered with a vault and the owner defines its Connection Contract. |

## License

Copyright © 2026 The VettID Project. This paper is licensed under the [Creative Commons Attribution 4.0 International License](LICENSE) (CC BY 4.0).
