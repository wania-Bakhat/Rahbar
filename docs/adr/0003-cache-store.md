# ADR 0003: Redis semantic cache with index generations

- Status: accepted
- Context: Repeated semantically similar questions should avoid repeated generation, but cached answers must not survive an index refresh as if based on the new corpus. The assignment NetworkPolicy allows Redis ingress from the API only.
- Decision: Redis stores semantic cache entries with a TTL and similarity threshold. The API reads Chroma's catalog `index_generation` metadata and includes the current generation in its Redis namespace. The indexer first builds a complete shadow collection and switches the catalog pointer; the new generation makes old keys unreachable, and their TTL reclaims them. The indexer never connects to or flushes Redis.
- Consequences: Cache invalidation follows index replacement while keeping Redis private to API pods. API requests need to read the generation marker; if Chroma is unavailable, normal retrieval is already unavailable. Old generation keys temporarily consume memory until TTL expires.
- Alternatives considered: An indexer-issued Redis flush violates the API-only NetworkPolicy. A shared fixed namespace risks stale answers. Redis persistence supports restart recovery but does not replace TTL or generation invalidation.
