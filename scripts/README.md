# Scripts

This directory contains helpers for setting up the environment and running the end-to-end demo.

## Setup scripts

- [install_env.ps1](install_env.ps1) creates a virtual environment and installs dependencies.
- [install_env.sh](install_env.sh) does the same from a shell environment.
- [activate.ps1](activate.ps1) activates the repo virtual environment in PowerShell.
- [activate.sh](activate.sh) activates the repo virtual environment in shell.

## Demo runner

- [run_login_lab_demo.ps1](run_login_lab_demo.ps1) starts the lab if needed, runs the attack client, and stops the lab when it started it.

Each run creates a timestamped folder under [login-lab/logs](../login-lab/logs/) containing `lab_stdout.log`, `lab_stderr.log`, and the attack CSVs for cli and web mode.

When you omit script arguments, the runner leaves attack configuration to the `ATTACK_*` values in [../attack/.env](../attack/.env).

Example:

```powershell
.\scripts\run_login_lab_demo.ps1 -Mode both -GeneratedRoot passwords/raw -Pattern *.txt
```

Add `-NoManageLab` if you already have the login lab running.