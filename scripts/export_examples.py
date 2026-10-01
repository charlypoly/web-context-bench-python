"""Copy one example of each representation, for one page, into results/examples/.

    uv run python scripts/export_examples.py <run_id> [page_id]   (default page: form)

Files are copied byte-for-byte from the audit copies the run saved, so readers
see exactly what the model saw (the Browser Use agent-default output is
included as an audit-only comparison and labeled as such).
"""

from __future__ import annotations

import shutil
import sys

from wpbench import RESULTS_DIR

FILES = {
    "raw_html.html": "1_raw_html.html",
    "markdown.md": "2_markdown.md",
    "accessibility_tree.yaml": "3_accessibility_tree.yaml",
    "indexed_dom.txt": "4_indexed_dom.txt",
    "stagehand_snapshot.txt": "5_stagehand_snapshot.txt",
    "screenshot.png": "6_screenshot.png",
    "indexed_dom.agent_default.audit_only.txt": "audit_only_indexed_dom_agent_default_cutoff.txt",
}


def main(run_id: str, page_id: str = "form") -> None:
    src = RESULTS_DIR / "representations" / run_id / "repeat1" / page_id
    dst = RESULTS_DIR / "examples" / page_id
    dst.mkdir(parents=True, exist_ok=True)
    for name, out in FILES.items():
        shutil.copyfile(src / name, dst / out)
    (dst / "SOURCE.txt").write_text(f"Copied from results/representations/{run_id}/repeat1/{page_id}/\n")
    print(f"exported {len(FILES)} files to {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:])
