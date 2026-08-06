# EventForge CI/CD

> **Archived deploy (ADR-015):** AWS ECS deploy and `deploy.yml` are **not maintained** during the dataset pivot. Current target is **LocalStack + workers locally**. The sections below document the historical AWS setup for portfolio reference.

## Active CI

GitHub Actions runs lint and tests on every PR and push to `main`.

| Workflow | Trigger | Purpose |
| -------- | ------- | ------- |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | PR + push `main` | Ruff, ESLint, pytest (`-m "not integration"`) |

No deploy workflow runs on merge. Terraform and ECS modules remain in `infra/terraform/` for reference only.

---

## Historical AWS deploy (archived)

Previously, GitHub Actions deployed EventForge to AWS **eu-west-2** on merge to `main` via `.github/workflows/deploy.yml` (removed during pivot).

### Workflows (historical)

| Workflow | Trigger | Purpose |
| -------- | ------- | ------- |
| `deploy.yml` | PR (terraform paths), push `main`, `workflow_dispatch` | ECR build/push, ECS rollout, Terraform plan/apply |

### Path filters (push to `main`)

| Paths | Job |
| ----- | --- |
| `backend/**` | Build backend image → roll out API + 6 workers |
| `frontend/**` | Build frontend (SSM `NEXT_PUBLIC_*`) → roll out frontend |
| `infra/terraform/**` | `terraform fmt` / `validate` / `plan` (PR) or `apply` (main) |

Manual deploy: **Actions → Deploy → Run workflow** → choose `backend`, `frontend`, `terraform`, or `all`.

### One-time AWS setup

#### 1. Apply Terraform (adds OIDC role + SSM build params)

After your first successful deploy, apply again to create the GitHub OIDC role and SSM parameters for frontend builds:

```bash
cd infra/terraform/environments/dev
terraform apply
```

If the GitHub OIDC provider already exists in your AWS account:

```hcl
# terraform.tfvars
create_github_oidc_provider = false
```

#### 2. GitHub repository configuration

**Important:** `AWS_DEPLOY_ROLE_ARN` must be a **repository variable**, not only a secret.

GitHub → **Settings → Secrets and variables → Actions**:

| Tab | Name | Value | Required |
| --- | ---- | ----- | -------- |
| **Variables** | `AWS_DEPLOY_ROLE_ARN` | Full IAM role ARN from Terraform output | **Yes (recommended)** |
| Secrets | `AWS_DEPLOY_ROLE_ARN` | Same ARN | Optional fallback |

Example value:

```text
arn:aws:iam::123456789012:role/eventforge-dev-github-actions
```

Get the ARN after `terraform apply`:

```bash
cd infra/terraform/environments/dev
terraform output -raw github_actions_role_arn
```

**Optional overrides** — defaults were hardcoded in `deploy.yml` (`env` block).

| Name | Default |
| ---- | ------- |
| `AWS_REGION` | `eu-west-2` |
| `ECS_CLUSTER_NAME` | `eventforge-dev-cluster` |
| `ECS_NAME_PREFIX` | `eventforge-dev` |
| `FRONTEND_BUILD_SSM_PATH` | `/eventforge/dev/frontend-build` |

**Repository secret** (for Terraform plan/apply in CI):

| Name | Content |
| ---- | ------- |
| `TFVARS_DEV` | Full contents of your `terraform.tfvars` (gitignored) |

#### 3. Remote Terraform state (recommended)

Uncomment the `backend "s3"` block in `environments/dev/main.tf`, create the bucket and lock table, then set in `terraform.tfvars`:

```hcl
terraform_state_bucket_name = "eventforge-terraform-state"
terraform_lock_table_name   = "eventforge-terraform-locks"
```

### How deploy worked

1. **OIDC** — workflow assumed `eventforge-dev-github-actions` (no static AWS keys).
2. **ECR** — images tagged with `${{ github.sha }}` and `latest`.
3. **ECS** — [`scripts/ci/ecs-deploy-service.sh`](../scripts/ci/ecs-deploy-service.sh) registered a new task definition revision with the new image and waited for service stability.
4. **Frontend build args** — read from SSM (`/eventforge/dev/frontend-build/NEXT_PUBLIC_*`), synced from Terraform on each apply.

### Local scripts (historical)

```bash
ECS_CLUSTER_NAME=eventforge-dev-cluster \
  ./scripts/ci/ecs-deploy-service.sh eventforge-dev-cluster eventforge-dev-api IMAGE_URI

ECS_CLUSTER_NAME=eventforge-dev-cluster BACKEND_IMAGE=IMAGE_URI \
  ./scripts/ci/ecs-deploy-backend.sh

./scripts/ci/frontend-build-args.sh
```

### Troubleshooting (historical)

| Symptom | Fix |
| ------- | --- |
| Deploy jobs skipped | Set `AWS_DEPLOY_ROLE_ARN` repository variable (full IAM role ARN) |
| `Source Account ID is needed...` | `AWS_DEPLOY_ROLE_ARN` must be full ARN, not just the role name |
| `AccessDenied` on ECR/ECS | Re-apply Terraform (`github_oidc` module) |
| Frontend build missing `NEXT_PUBLIC_*` | `terraform apply` (writes SSM) or check `frontend_build_ssm_path` output |
| Terraform apply fails in CI | Add `TFVARS_DEV` secret; enable S3 remote backend |
| OIDC provider already exists | `create_github_oidc_provider = false` |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | Confirm `github_repo` in Terraform matches the real GitHub repo name |

See also: [`docs/ISSUES.md`](./ISSUES.md) for STAR postmortems on CI/OIDC/Terraform issues.
