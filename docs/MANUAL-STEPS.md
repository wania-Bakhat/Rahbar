# Manual steps for the student/team

These actions require your GitHub/Classroom account or your personal experience. Do not
replace them with fabricated screenshots, links, or reflections.

## Restore Docker/Minikube space before the final live evaluation

The C: drive has 0 bytes free. Minikube reported that it could not write its API image cache,
Docker container inspection took about 19 seconds and timed out, and the API's request-time
Ollama embedding call returned a timeout. The Kubernetes API still answered some commands,
but q09 could not reach generation. Do these steps before asking for the final live rerun:

1. Open **Windows Settings → System → Storage → Temporary files**.
2. Review the categories. Select temporary files you recognize and can remove; leave
   **Downloads** unchecked unless you personally reviewed its contents. Click **Remove files**.
   Free several GB so Docker/Minikube can write their image cache.
3. Close Docker Desktop from its tray menu, reopen it, and wait until the bottom-left says
   **Engine running**.
4. In a new PowerShell terminal at the repository root, run:

   ```powershell
   Get-PSDrive C | Select-Object Name,Free
   docker info --format '{{.OSType}}'
   minikube status
   kubectl get nodes
   kubectl get pods -n rahbar
   ```

   Confirm C: has free space, Docker prints `linux`, Minikube reports host/kubelet/apiserver
   Running, and the node is Ready. Do not delete the Minikube profile or Docker volumes.
5. Tell Codex the outputs. We will recheck the current Minikube-to-Ollama route, verify a
   768-dimensional embedding from inside the cluster, run q09 against the updated API, and
   rerun the full evaluation before accepting a new baseline.

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
