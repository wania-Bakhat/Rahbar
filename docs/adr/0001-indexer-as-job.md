# ADR 0001: Run indexing as a Kubernetes Job

- Status: accepted
- Context: Indexing is batch work over a fixed corpus. The API must serve requests and must not build or mutate the index during its lifecycle.
- Decision: Run the indexer as a Kubernetes Job for controlled indexing and a CronJob for scheduled refresh. Both use the same image, corpus PVC, configuration, resource limits and restricted service account. The API Deployment reads Chroma only.
- Consequences: Index work can be retried and observed independently from API rollouts. The Job builds a uniquely named collection, verifies its count, and then publishes it by updating a Chroma catalog pointer; API readers continue using the old complete collection during the build. The active and immediately previous collection are retained. A successful publication writes an `index_generation` marker; API requests detect the marker and switch cache namespaces. The Job requires the corpus PVC to be populated and Chroma to be ready.
- Alternatives considered: Index on API startup would couple serving availability to batch work and could race across replicas; a permanently running indexer service would waste resources and complicate coordination.
