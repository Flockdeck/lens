# Deploying session-lens

Manifests live in `deploy/k8s-infra/session-lens/` and are applied by Flux. One image
(`ghcr.io/jmwri/session-lens`, built by CI on `v*` tags, tagged with plain semver) runs as:

| Workload | Command | Notes |
| --- | --- | --- |
| `session-lens-api` Deployment | `session-lens api` | init container runs `session-lens migrate`; probes `/healthz`, `/readyz`; port 8000 |
| `session-lens-worker` Deployment | `session-lens worker` | no inbound traffic; safe to scale (SKIP LOCKED) |
| `session-lens-cleanup` CronJob | `session-lens cleanup` | daily 03:17, marks rows whose raw recording is past retention as expired and prunes old batches (database only, never touches the bucket) |

## What terrawost must provision

1. **Namespace** `session-lens`.
2. **MySQL 8** database `session_lens` and a user with full rights on it. The NetworkPolicy
   allows ports 25060 (managed) and 3306.
3. **Secret `session-lens-secret`** in the namespace with keys:
   - `databaseUrl`: `mysql+asyncmy://USER:PASSWORD@HOST:25060/session_lens?charset=utf8mb4`
     (add TLS options as the managed database requires)
   - `apiToken`: long random bearer token for the API and UI
   - `anthropicApiKey`: Anthropic API key used by the worker (`ENRICHER=anthropic`)
   - `s3EndpointUrl`, `s3Region`, `s3Bucket`, `s3AccessKey`, `s3SecretKey`: the Spaces bucket
     below (`S3_ENDPOINT_URL` such as `https://ams3.digitaloceanspaces.com`); read by the api,
     worker and cleanup CronJob
4. **Spaces bucket** (raw recordings live here, not in MySQL) with a lifecycle rule expiring
   objects under `recordings/` after 30 days. This must equal `RAW_RETENTION_DAYS` (set to
   `"30"` in the manifests); the app never sweeps the bucket. Create an access key scoped to
   this bucket only and put it in the secret. No MySQL `max_allowed_packet` change is needed.
5. **DNS** `session-lens.jmwri.dev` pointing at the HAProxy ingress.
6. **Flux** wiring for the `session-lens` directory, including `registry.yaml`
   (ImageRepository/ImagePolicy in `flux-system`) and image-update automation, as for vael.
7. Assumed to exist already: HAProxy ingress in namespace `haproxy-ingress`, cert-manager
   with ClusterIssuer `letsencrypt-prod`, CoreDNS (`k8s-app: kube-dns`).
8. A public GHCR package (or an imagePullSecret) for `ghcr.io/jmwri/session-lens`.

## Notes

- The API enforces the ~256 MiB request limit (`MAX_REQUEST_BYTES`); the HAProxy ingress has
  no body-size annotation, so only the client/server timeouts are raised.
- Egress to `api.anthropic.com` and the Spaces endpoint is allowed as TCP 443 to public
  addresses, since a NetworkPolicy cannot match hostnames.
- Prometheus is not in the cluster; `/metrics` is exposed by the API for when it is.
