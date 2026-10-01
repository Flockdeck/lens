# Deploying session-lens

Manifests live in `deploy/k8s-infra/session-lens/` and are applied by Flux. One image
(`ghcr.io/jmwri/session-lens`, built by CI on `v*` tags, tagged with plain semver) runs as:

| Workload | Command | Notes |
| --- | --- | --- |
| `session-lens-api` Deployment | `session-lens api` | init container runs `session-lens migrate`; probes `/healthz`, `/readyz`; port 8000 |
| `session-lens-worker` Deployment | `session-lens worker` | no inbound traffic; safe to scale (SKIP LOCKED) |
| `session-lens-cleanup` CronJob | `session-lens cleanup` | daily 03:17, deletes raw recordings past retention |

## What terrawost must provision

1. **Namespace** `session-lens`.
2. **MySQL 8** database `session_lens` and a user with full rights on it. The NetworkPolicy
   allows ports 25060 (managed) and 3306.
3. **Secret `session-lens-secret`** in the namespace with keys:
   - `databaseUrl`: `mysql+asyncmy://USER:PASSWORD@HOST:25060/session_lens?charset=utf8mb4`
     (add TLS options as the managed database requires)
   - `apiToken`: long random bearer token for the API and UI
   - `anthropicApiKey`: Anthropic API key used by the worker (`ENRICHER=anthropic`)
4. **DNS** `session-lens.jmwri.dev` pointing at the HAProxy ingress.
5. **Flux** wiring for the `session-lens` directory, including `registry.yaml`
   (ImageRepository/ImagePolicy in `flux-system`) and image-update automation, as for vael.
6. Assumed to exist already: HAProxy ingress in namespace `haproxy-ingress`, cert-manager
   with ClusterIssuer `letsencrypt-prod`, CoreDNS (`k8s-app: kube-dns`).
7. A public GHCR package (or an imagePullSecret) for `ghcr.io/jmwri/session-lens`.

## Notes

- The API enforces the ~256 MiB request limit (`MAX_REQUEST_BYTES`); the HAProxy ingress has
  no body-size annotation, so only the client/server timeouts are raised.
- Egress to `api.anthropic.com` is allowed as TCP 443 to public addresses, since a
  NetworkPolicy cannot match hostnames.
- Prometheus is not in the cluster; `/metrics` is exposed by the API for when it is.
