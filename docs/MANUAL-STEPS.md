# Manual steps for the student/team

These actions require your GitHub/Classroom account or your personal experience. Do not
replace them with fabricated screenshots, links, or reflections.

## Restore local cluster access before live demonstrations

Docker Desktop's named pipe stopped responding, and `minikube status` timed out while
inspecting the existing `minikube` container. To resume live tuning and Kubernetes evidence:

1. Open Docker Desktop and wait until its bottom-left status says **Engine running**.
2. In a PowerShell terminal at the repository root, run:

   ```powershell
   docker info --format '{{.OSType}}'
   minikube status
   ```

3. The first command should print `linux`. If `minikube status` says the profile is stopped,
   run `minikube start --driver=docker --cni=calico --memory=6144 --cpus=4`, then enable
   `metrics-server` and `ingress` addons if they are not enabled.
4. Leave Docker Desktop running and tell Codex the two command outputs. Do not delete the
   Docker volumes or the repository; the existing Chroma index and evidence depend on them.

## GitHub repository secrets

1. Create a Docker Hub access token in Docker Hub (do not use the account password).
2. Open the GitHub repository → **Settings → Secrets and variables → Actions**.
3. Add repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
4. After `dev` is merged into `main` through the protected PR, confirm the `CD` workflow
   builds and publishes all three images tagged with the commit SHA.

## Protect `main`

1. Open repository **Settings → Rules → Rulesets** (or **Branches → Branch protection**).
2. Target branch `main`; require a pull request before merging and require one approval.
3. Require the CI status checks (lint, test, manifests, build, scan, e2e-eval) before
   merging. Disable direct pushes if the available settings allow it.
4. Save the real settings page screenshot to `docs/evidence/branch-protection.png`.

## Required GitHub screenshots

1. Open the dev-to-main pull request while its evaluation check is failing; screenshot the
   disabled/blocked merge control as `docs/evidence/blocked-merge.png`.
2. After fixing all CI failures, screenshot the passing checks/merge-ready state as
   `docs/evidence/green-merge.png`.
3. Do not create sample/mock screenshots. Keep the screenshots from the actual repository.

## Review AI disclosure

Both partners review `docs/AI-USAGE.md`, confirm the listed tools and AI-shaped work,
add any tools they used independently, and explain any substantive changes they made.

## Personal engineering reflection

Write the response to question 7 in `docs/ENGINEERING-NOTES.md` from your own notes:
describe the task that took over an hour, what you first believed incorrectly, the exact
command/log/metric that revealed the cause, the fix, and how you verified it. Do not copy
someone else's story or use AI to invent a personal experience.

## Google Classroom submission

Submit one team entry before the PDF deadline with: repository URL (public or instructors
added if private), successful `cd.yml` run link, links to the three SHA-tagged Docker Hub
images, and committed `eval/results.json` plus `eval/baseline.json`. Include the required
evidence files and confirm both partners understand and reviewed the work.
