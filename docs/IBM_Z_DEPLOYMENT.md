# IBM Z / LinuxONE verification runbook

**Status:** prepared instructions only. No access to an IBM Z or LinuxONE VM was available in this checkout; no `s390x` test, deployment or performance result is claimed.

## 1. Provision an authorized VM

Use the [LinuxONE Community Cloud](https://linuxone.cloud.marist.edu/) portal and current organizer instructions. The [community ML example](https://github.com/linuxone-community-cloud/jupyter-lab-ml) documents SSH-key and VM provisioning, but its container/Jupyter setup is optional and is not a FRAUDSHIELD dependency. Confirm the VM username, hostname and access method in the portal. Keep SSH private keys outside the repository.

## 2. Transfer only tracked source

From the committed feature branch on your laptop:

```bash
git archive --format=tar.gz --output=/tmp/fraudshield-source.tgz HEAD
scp /tmp/fraudshield-source.tgz <username>@<VM_HOST>:~/
ssh <username>@<VM_HOST>
```

`git archive` excludes untracked local SQLite files, downloaded PaySim CSVs and local model artifacts. Do not transfer customer data, secrets or the demo's local database.

On the VM:

```bash
umask 077
mkdir -p ~/eidolon-fraudshield
tar -xzf ~/fraudshield-source.tgz -C ~/eidolon-fraudshield
cd ~/eidolon-fraudshield
uname -m
python3 --version
python3 -B -m unittest discover -s tests -v
python3 run.py
```

Record the actual output. Proceed only if `uname -m` prints `s390x`, Python is 3.10 or newer, and the tests pass. The project uses Python's standard library and SQLite module; check `python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'` if SQLite is missing. The server binds to loopback and rejects wider binding.

## 3. View through an SSH tunnel

In a second laptop terminal:

```bash
ssh -L 8000:127.0.0.1:8000 <username>@<VM_HOST>
```

Open `http://127.0.0.1:8000` on the laptop. Confirm `/api/health`, run the synthetic replay, score a manual event, refresh the page and record a review disposition. Verify the event and review survive a server restart. The app does not require Docker, paid APIs or public HTTP exposure.

## 4. Capture reproducible evidence

Save the VM architecture, OS and Python versions, exact Git commit, full test output, health response, synthetic replay count, restart/readback result and a timestamped screenshot. Remove hostnames, usernames, keys and any sensitive data before sharing. Label the dashboard metrics as synthetic. If measuring latency or throughput, record the command, dataset/fixture, concurrency, sample count and host details; report measured values only. A laptop run or an emulated `s390x` environment does not establish deployment on actual LinuxONE hardware.

## 5. Failure handling

- If `uname -m` differs from `s390x`, stop and verify the provisioned VM.
- If Python is older than 3.10, use an organizer-supported interpreter; do not change the app's language requirement silently.
- If the suite fails, preserve the output and fix the cause before claiming verification.
- If the tunnel is unavailable, use only an organizer-approved private access method. Never bind this unauthenticated demo to `0.0.0.0`.
- If the default port is occupied, use `PORT=8001 python3 run.py` and `ssh -L 8001:127.0.0.1:8001 ...`.
