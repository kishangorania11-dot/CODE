#!/usr/bin/env python3
"""One-off discovery script: inspects the API surface of a SadTalker
Hugging Face Space so we know the exact input/output parameter names
before building the real generation script."""

from gradio_client import Client

SPACE_CANDIDATES = [
    "vinthony/SadTalker",
    "kevinwang676/SadTalker",
    "abreza/SadTalker",
]


def main():
    for space in SPACE_CANDIDATES:
        print(f"\n=== Inspecting {space} ===")
        try:
            client = Client(space)
            client.view_api(print_info=True)
        except Exception as exc:
            print(f"Failed to inspect {space}: {exc}")


if __name__ == "__main__":
    main()
