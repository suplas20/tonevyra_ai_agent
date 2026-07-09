# Bundled Runtime Distribution Skill

## Purpose

Use this skill to create reproducible app-local runtime payloads, especially the exact Python 3.11.9 environment required by Tonevyra.

## Mandatory Rules

- Python version is exactly 3.11.9.
- Runtime and dependencies are included in the application payload.
- Do not modify PATH, file associations, Python Launcher, pyenv or Homebrew.
- Do not run public `pip install` during end-user installation or first launch.
- Generate a locked dependency inventory, file hashes and license inventory.
- Test imports and native-library loading on clean target systems.
- The application must report `runtime_source=bundled`.

## Release Gate

A build fails if the bundled runtime uses a different interpreter version, imports from outside the install root, or contains an unreviewed binary dependency.
