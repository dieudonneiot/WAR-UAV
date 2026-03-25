from __future__ import annotations

import importlib

PACKAGES = [
    "numpy",
    "cv2",
    "ultralytics",
    "pymavlink",
    "mavsdk",
    "yaml",
    "dotenv",
    "rich",
]


def main() -> None:
    print("Environment package check:")
    for name in PACKAGES:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "version-not-exposed")
        print(f"  - {name}: {version}")


if __name__ == "__main__":
    main()

