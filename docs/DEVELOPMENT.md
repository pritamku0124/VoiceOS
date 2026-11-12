# Development Guide

## Daily workflow

```powershell
cd D:\project\VoiceOS
.\.venv\Scripts\Activate.ps1   # prompt now starts with (.venv)
python main.py                 # run the app
python -m pytest               # run all tests
python -m pytest -v tests\test_config_service.py   # one file, verbose
deactivate                     # leave the virtual environment
```

## Conventions

- **Imports are absolute from the project root**: `from services.config_service import ConfigService`.
- **No `print` in app code.** Use `logger = logging.getLogger(__name__)`.
- **Paths come from `utils/constants.py`**, never hard-coded strings.
- **Raise `VoiceOSError` subclasses** for expected problems; let real bugs crash loudly in development.
- **Every new module gets tests** in `tests/`. Tests must not touch the real `config.json` (use `tmp_path`).
- **Placeholders**: a file whose docstring says "planned for Phase N" is intentionally empty.

## Adding a dependency

1. Check it has a Windows wheel for Python 3.14 (see INSTALLATION.md).
2. Add it with an exact version to `requirements.txt` (or `requirements-dev.txt` for dev tools).
3. `python -m pip install -r requirements-dev.txt`
4. Update the table in INSTALLATION.md.

## Logs

`logs\voiceos.log` holds the most recent run's details. It rotates at 1 MB and keeps 3 old files.
