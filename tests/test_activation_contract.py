"""Tests for CLI entrypoint smoke testing and reproducible ingest outputs."""

import json
import sys

from alchemia.absorb.classifier import classify_all
from alchemia.cli import main
from alchemia.intake.crawler import crawl
from alchemia.intake.dedup import mark_duplicates


def test_cli_help_smoke(capsys, monkeypatch):
    """Verify CLI main entrypoint executes help without error."""
    monkeypatch.setattr(sys, "argv", ["alchemia", "--help"])
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    captured = capsys.readouterr()
    assert "The Alchemical Forge" in captured.out


def test_cli_status_smoke(capsys, monkeypatch):
    """Verify CLI status entrypoint executes without error."""
    monkeypatch.setattr(sys, "argv", ["alchemia", "status"])
    main()
    captured = capsys.readouterr()
    assert "intake-inventory.json" in captured.out


def test_reproducible_ingest_output(tmp_path):
    """Verify that intake crawling and classification produce deterministic outputs."""
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "sample1.txt").write_text("Hello world organvm-i-theoria")
    (src_dir / "sample2.py").write_text("print('test')")

    repo_info = {"name": "organvm-i-theoria", "organ": "ORGAN-I", "org": "meta-organvm"}
    registry = {
        "repos": [repo_info],
        "by_name": {"organvm-i-theoria": repo_info},
        "by_org": {},
        "archived": set(),
    }

    inv1 = mark_duplicates(crawl([src_dir]))
    class1 = classify_all(inv1, registry)
    inv2 = mark_duplicates(crawl([src_dir]))
    class2 = classify_all(inv2, registry)

    out1 = json.dumps(class1, sort_keys=True)
    out2 = json.dumps(class2, sort_keys=True)

    assert out1 == out2, "Ingest outputs are not reproducible"
