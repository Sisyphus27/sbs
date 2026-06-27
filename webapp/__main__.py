"""Entry point: python -m webapp  -> starts local server + opens browser.
Absolute import so PyInstaller (which runs this as a top-level script) resolves it."""
from webapp.app import run

if __name__ == "__main__":
    run()
