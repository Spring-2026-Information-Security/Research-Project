# Research Project Overview

This repository is organized around a small login lab, a reusable attack client, and helper scripts for repeatable demo runs.

## Layout

- [login-lab/](login-lab/) contains the Flask target, UI, API, and lab-specific configuration.
- [attack/](attack/) contains the password-guessing client and attack-specific configuration.
- [scripts/](scripts/) contains setup helpers and the one-command demo runner.
- [passwords/](passwords/) contains generated and downloaded password corpora.

## Quick Start

1. Install dependencies from the repository root.
2. Read [login-lab/README.md](login-lab/README.md) for the target lab.
3. Read [attack/README.md](attack/README.md) for the client.
4. Read [scripts/README.md](scripts/README.md) for the automated demo runner.

## Configuration

- [login-lab/.env](login-lab/.env) holds the lab defaults.
- [attack/.env](attack/.env) holds the client defaults.
- Command-line arguments still override env values when provided.