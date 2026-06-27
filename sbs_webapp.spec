# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: bundle the webapp + sbs_cli engine + templates/static
into a single exe. DB is resolved next to the exe at runtime (see webapp/db.py)."""

datas = [
    ("webapp/templates", "webapp/templates"),
    ("webapp/static", "webapp/static"),
]
hiddenimports = [
    "sbs_cli", "sbs_cli.engine.progression", "sbs_cli.engine.onerm",
    "sbs_cli.program", "sbs_cli.data.schema", "sbs_cli.data.io",
    "sbs_cli.importer", "jinja2",
]

a = Analysis(["webapp/__main__.py"], pathex=[], binaries=[], datas=datas,
             hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
             excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="sbs_webapp",
          console=True, onefile=True)
