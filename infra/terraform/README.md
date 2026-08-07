# Terraform Infrastructure

> **ADR:** [ADR-012](../../docs/TECH_DECISIONS.md#adr-012-all-in-aws-deployment-on-ecs-fargate) — all-in-AWS ECS Fargate deployment.  
> **Architecture doc:** [`docs/AWS_ARCHITECTURE.md`](../../docs/AWS_ARCHITECTURE.md) — Mermaid diagrams and portfolio walkthrough (archived, not maintained).  
> **Cursor agents:** Infra conventions in `.cursor/rules/infra-aws.mdc`.

IaC for AWS resources. Default region: **`eu-west-2` (London)**.

## Structure

```
terraform/
├── environments/
│   └── dev/                 # networking + rds + sqs + eventbridge + ecs
└── modules/
    ├── networking/          # VPC, subnets, NAT, security groups ✅
    ├── rds/                 # Postgres 16 + Secrets Manager password ✅
    ├── sqs/                 # Worker queues + DLQ + redrive ✅
    ├── eventbridge/         # Bus + stage routing rules ✅
    ├── ecs/                 # ECR, cluster, ALB, Fargate services ✅
    ├── github-oidc/         # GitHub Actions OIDC IAM role ✅
    ├── step-functions/      # Research fan-out Map workflow ✅
    └── observability/       # ADOT sidecar config, CloudWatch alarms ✅
```

## What exists today

| Module             | Resources                                                                                                                                 |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **networking**     | VPC `/16`, 2 AZs, public + private subnets, NAT (single for dev), SGs for ALB/API/frontend/workers/RDS                                    |
| **rds**            | Postgres 16 (gp3), subnet group, backups, password in Secrets Manager; pgvector via Alembic on migrate                                    |
| **sqs**            | `eventforge-*` worker queues + DLQ, redrive policies (mirrors LocalStack init)                                                            |
| **eventbridge**    | `eventforge-bus` + rules routing each `detail-type` to the next stage queue                                                               |
| **ecs**            | ECR repos, ECS cluster, ALB (SSE idle timeout 300s), API + frontend + 6 worker services; optional ADOT sidecar when observability enabled |
| **observability**  | ADOT collector config, DLQ + API task CloudWatch alarms                                                                                   |
| **step-functions** | Research fan-out Map state machine (optional via `enable_step_functions_research`)                                                        |

`environments/dev` wires **networking → rds → sqs → eventbridge → step-functions → observability → ecs**. LLM API keys remain **manual Secrets Manager ARNs** in tfvars.

Set `enable_observability = true` (default) to add an ADOT sidecar on API/worker tasks exporting traces to X-Ray (`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317`).

### Frontend Docker build (prod)

Use `terraform output -json frontend_build_env` for `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_APP_URL` build args. The frontend `Dockerfile` accepts these as build args.

## Prerequisites

- Terraform >= 1.5
- AWS CLI configured (`aws sts get-caller-identity`)
- IAM permissions for VPC, RDS, ECS, ECR, ALB, IAM, CloudWatch Logs, Secrets Manager

## Git / secrets

Do **not** commit `terraform.tfvars`, `*.tfstate`, or `*.tfplan` (see root `.gitignore`).  
**Do** commit `.terraform.lock.hcl` under `environments/dev/` for reproducible provider versions.

## Quick start (dev)

```bash
cd infra/terraform/environments/dev

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — images, LLM secret ARNs, app_base_url after first apply

terraform init
terraform plan
terraform apply
```

### First deploy order

1. `terraform apply` with placeholders only for **networking + ECR** — or apply networking first by temporarily commenting the ecs module
2. Build and push images:

```bash
# From repo root — use ECR URLs from terraform output
aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.eu-west-2.amazonaws.com

docker build -t eventforge-dev-backend backend/
docker tag eventforge-dev-backend:latest $(terraform output -raw backend_ecr_repository_url):latest
docker push $(terraform output -raw backend_ecr_repository_url):latest

docker build -t eventforge-dev-frontend \
  --build-arg NEXT_PUBLIC_API_URL=http://$(terraform output -raw alb_dns_name) \
  $(terraform output -json frontend_build_env | jq -r 'to_entries | map("--build-arg \(.key)=\(.value)") | join(" ")') \
  frontend/
docker tag eventforge-dev-frontend:latest $(terraform output -raw frontend_ecr_repository_url):latest
docker push $(terraform output -raw frontend_ecr_repository_url):latest
```

3. Set `app_base_url` and `cors_origins` from `terraform output alb_dns_name`, then re-apply
4. Rebuild frontend using `terraform output -json frontend_build_env` for `--build-arg` values; push images and re-apply if needed

After first apply, run Alembic migrations via the API task (entrypoint runs `alembic upgrade head` on deploy) or connect to RDS from a bastion/session for manual verify. The `vector` extension is created by Alembic migration `5f4297155502`.

## Remote state (recommended before team use)

Uncomment the `backend "s3"` block in `environments/dev/main.tf` and create:

- S3 bucket `eventforge-terraform-state` (versioning + encryption)
- DynamoDB table `eventforge-terraform-locks`

## Next modules

1. Secrets module for OpenAI/Tavily keys (optional; manual SM secrets work for dev)
2. Phase 6 — Playwright E2E, DLQ replay UI, demo GIF

**CI/CD:** GitHub Actions deploy — see [`docs/CICD.md`](../../docs/CICD.md). Set repo variable `AWS_DEPLOY_ROLE_ARN` from `terraform output github_actions_role_arn`.

**Auth:** Cognito removed per ADR-013. Dev ALB exposes an open API (mock user only).
