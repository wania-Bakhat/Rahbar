# ADR 0004: Configurable LLM provider and data governance

- Status: accepted
- Context: The service answers from institutional documents and should not disclose student records or send private data to an external provider. Local development and CI also need deterministic behavior without paid model access.
- Decision: Keep provider selection in configuration, default the Kubernetes deployment to the host Ollama provider, and use stub/test-only providers in local or CI scenarios. Only retrieved public corpus excerpts and the question are sent to the configured model. Store API credentials in Kubernetes Secrets or CI secrets, never in Git or container layers. Treat returned answers as untrusted output and enforce the answer schema, context sufficiency and citation checks in the API.
- Consequences: A hosted provider requires a user-supplied secret and appropriate data-governance review; local Ollama requires reachable network egress and installed models. The service must not ingest personal student records. The repository does not claim formal provider privacy guarantees beyond this data-flow design.
- Alternatives considered: Hard-coding credentials or provider endpoints would expose secrets and make deployment non-portable. Sending unrestricted questions/context to an arbitrary provider would violate the stated data minimization approach.
