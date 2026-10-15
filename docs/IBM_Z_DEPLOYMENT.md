# IBM Z / LinuxONE deployment runbook

## 1. Register and provision

Event instructions specify [LinuxONE Community Cloud](https://linuxone.cloud.marist.edu/#/register?flag=VM) and event code **SSF2026**. Complete the **mandatory Oct 16, 2026 7:30 PM IST** onboarding session and follow current organizer guidance. Add team/project description to the VM application. Configure your own SSH key. Do not commit private SSH keys.

The organizer-provided [LinuxONE ML examples](https://github.com/linuxone-community-cloud/jupyter-lab-ml) include an existing fraud-detection notebook. Unlike that optional example, FRAUDSHIELD does **not** require Docker or JupyterLab to run; it is a standard-library Python program.

## 2. Transfer project

From your laptop, once the VM's SSH username and hostname have been confirmed by the provider:

```bash
scp -r eidolon-fraudshield <username>@<VM_HOST>:~/
ssh <username>@<VM_HOST>
```

Set restrictive permissions for local data and run:

```bash
cd ~/eidolon-fraudshield
uname -m                 # record architecture, expected s390x
python3 --version        # requires Python >=3.10
python3 -m unittest discover -s tests -v
python3 run.py
```

The app listens **only on 127.0.0.1:8000** by default; this is intentional.

## 3. View remotely over SSH tunnel

In a second terminal on your laptop:

```bash
ssh -L 8000:127.0.0.1:8000 <username>@<VM_HOST>
```

Then browse `http://127.0.0.1:8000` locally. Do not blindly bind to `0.0.0.0` or open the unauthenticated demo service to the Internet. If the cloud provider restricts tunneling, use an organizer-approved access method instead.

## 4. Record proof of actual IBM Z use

- Save `uname -m`, `python3 --version`, local test output, VM details (without secrets) and a UI screenshot.
- Capture a timed replay, event scoring and a recorded review decision.
- Collect **actual hardware** latency/throughput measurements. Do not claim IBM Z speedups until a fair baseline comparison is run.
- Ensure the project is on LinuxONE before submission and explicitly link the implementation to IBM Z in the pitch.

## 5. Troubleshooting

- Port busy: `PORT=8001 python3 run.py` plus matching tunnel port mapping.
- Python too old: use a supported Python 3.10+ environment following the LinuxONE instructions.
- No outside networking: perform install/transfer over permitted SCP/SSH channels; no third-party Python packages are needed.
- If Jupyter Lab is required by the organizers, consult the [official community example repository](https://github.com/linuxone-community-cloud/jupyter-lab-ml) rather than changing this prototype to require a container.
