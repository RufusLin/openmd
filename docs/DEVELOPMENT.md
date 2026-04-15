# openmd Development Workflow

To maintain consistency across the repository and ensure correct packaging, follow this workflow for all changes.

## Source of Truth
- **`src/openmd.py`** is the primary source file. All code changes MUST be made here.

## Version Management
1.  **Bump Version:** Before every release or major feature push, update the version number in:
    - `pyproject.toml` (`version = "x.y.z"`)
    - `src/openmd.py` (top comment `# Version: x.y.z` AND the `__version__` variable)

## Build and Synchronization
1.  **Sync Root Executable:** After editing and testing `src/openmd.py`, synchronize it to the root directory for local convenience:
    ```bash
    cp src/openmd.py openmd
    chmod +x openmd
    ```
2.  **Verify README:** Ensure `README.md` reflects any new features, shortcuts, or dependency changes.

## Packaging
- The `pyproject.toml` uses the `src` layout:
  ```toml
  [tool.setuptools]
  package-dir = {"" = "src"}
  py-modules = ["openmd"]
  ```
- This ensures `pip install .` correctly installs the updated code from `src/`.

## Local Testing
- To test the current development version:
  ```bash
  python3 src/openmd.py path/to/file.md
  ```
- To test the synchronized root executable:
  ```bash
  ./openmd path/to/file.md
  ```
