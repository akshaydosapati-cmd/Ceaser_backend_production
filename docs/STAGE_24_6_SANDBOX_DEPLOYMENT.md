# CEASER Stage 24.6 Sandbox Deployment

## Current production status

The current Render worker uses the native Python runtime. It does not expose a
Docker daemon, Firecracker, Kubernetes Jobs, or another isolated execution
service. `SANDBOX_PROVIDER=unavailable` is therefore intentional: project build
jobs remain `WAITING_FOR_RESOURCE` and no model-generated command runs on the
Render worker host.

Do not set `SANDBOX_PROVIDER=docker` on the current Render native worker.

## Docker development provider

Build the dedicated image from `docker/sandbox/Dockerfile` and publish it to an
approved registry. Configure a separate sandbox-capable worker:

```text
SANDBOX_PROVIDER=docker
SANDBOX_DOCKER_IMAGE=<immutable-image-reference>
SANDBOX_NETWORK_MODE=none
SANDBOX_COMMAND_TIMEOUT_SECONDS=120
SANDBOX_MEMORY_MB=512
SANDBOX_CPU_LIMIT=1.0
SANDBOX_PIDS_LIMIT=128
SANDBOX_MAX_OUTPUT_BYTES=1048576
SANDBOX_MAX_FILES=5000
SANDBOX_MAX_BUILD_RETRIES=2
```

The worker host needs Docker Engine access, but the Docker socket must never be
mounted into a job container. Each job receives a read-only root filesystem,
ephemeral `/workspace`, no host bind mounts, a non-root user, dropped Linux
capabilities, `no-new-privileges`, and configured CPU/memory/PID limits.

## Network policy

The default is `none`. This blocks package installation and Git network access.
`bridge` may be enabled only on a dedicated sandbox worker with external
firewall/egress controls. Docker bridge mode alone cannot reliably block cloud
metadata endpoints, internal networks, or arbitrary destinations; it is not a
complete production egress policy.

## Production requirement

Use one of these before enabling cloud coding publicly:

1. A dedicated Docker worker VM with firewall-enforced egress and no backend
   source or production secrets on the host.
2. A remote sandbox provider with per-job microVM/container isolation and
   explicit egress policy.
3. Kubernetes Jobs with hardened pod security, network policies, resource
   quotas, ephemeral volumes, and per-job identities.

The CEASER worker should receive database and artifact-storage credentials.
Sandbox containers receive none of them. Durable source archives, manifests,
verification logs, and checkpoints are transferred by the worker through the
Stage 24 storage layer.

## Sandbox image toolchains

The supplied image definition contains:

- Node.js 22 and npm
- Python 3 and pip
- Git
- tar and CA certificates

Pin the published image by digest for production. Do not install toolchains on
the worker host at job runtime.
