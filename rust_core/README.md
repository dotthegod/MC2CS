# rust_core

This directory contains the optional Rust extension used to accelerate mesh-building.

Quick build / install (development):

```powershell
# from project root
cd rust_core
python -m pip install --upgrade maturin
maturin develop --release
```

Build a wheel:

```powershell
cd rust_core
maturin build --release
pip install target\wheels\mctocs_rust-*.whl
```

Notes:
- Requires a stable Rust toolchain and a working Python development environment.