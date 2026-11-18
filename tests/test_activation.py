"""Activation tests: packaging, release contract, and reproducibility.

These tests prove the #4 activation audit's contract: the package builds
into an installable wheel, the installed wheel runs the documented smoke
commands, the ingest stage is reproducible, and seed.yaml names the
release workflow, install/smoke commands, and promotion criteria.
"""

import json
import subprocess
import sys
import tomllib
import venv
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest
import yaml

from alchemia import cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def built_dist(tmp_path_factory):
    """Build the sdist + wheel once per session into a temp directory."""
    outdir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(outdir), str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return outdir


def test_build_artifact_has_entrypoint_and_version(built_dist):
    """The build produces one wheel + one sdist; the wheel exposes the
    alchemia console script and its version matches pyproject.toml."""
    wheels = sorted(built_dist.glob("*.whl"))
    sdists = sorted(built_dist.glob("*.tar.gz"))
    assert len(wheels) == 1, [p.name for p in built_dist.iterdir()]
    assert len(sdists) == 1, [p.name for p in built_dist.iterdir()]

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]
    assert version in wheels[0].name

    with zipfile.ZipFile(wheels[0]) as zf:
        entry_points = [n for n in zf.namelist() if n.endswith("entry_points.txt")]
        assert entry_points
        text = zf.read(entry_points[0]).decode()
    assert "alchemia = alchemia.cli:main" in text


def test_installed_wheel_smoke(built_dist, tmp_path):
    """The built wheel installs in a clean venv and the smoke commands
    exit 0: `alchemia --help` and the non-destructive `alchemia status`."""
    wheel = next(built_dist.glob("*.whl"))
    venv_dir = tmp_path / "venv"
    venv.create(venv_dir, with_pip=True)
    bin_dir = venv_dir / "bin"

    install = subprocess.run(
        [str(bin_dir / "pip"), "install", str(wheel)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    exe = bin_dir / "alchemia"
    help_run = subprocess.run(
        [str(exe), "--help"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert help_run.returncode == 0
    assert "alchemia" in help_run.stdout

    status_run = subprocess.run(
        [str(exe), "status"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert status_run.returncode == 0
    assert "not found" in status_run.stdout


def test_intake_is_deterministic(tmp_path):
    """Running intake twice on a fixed fixture produces byte-identical
    output: the ingest stage is reproducible, not order-dependent."""
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "a.md").write_text("# A\n")
    (source / "sub" / "b.md").write_text("# B\n")
    (source / "c.txt").write_text("plain\n")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("path,title\n")

    out1 = tmp_path / "inv1.json"
    out2 = tmp_path / "inv2.json"
    cli.cmd_intake(
        Namespace(source_dir=[str(source)], manifest=str(manifest), output=str(out1)),
    )
    cli.cmd_intake(
        Namespace(source_dir=[str(source)], manifest=str(manifest), output=str(out2)),
    )

    assert out1.read_bytes() == out2.read_bytes()
    assert len(json.loads(out1.read_text())["entries"]) == 3


def test_seed_yaml_names_release_contract():
    """seed.yaml names the release workflow, the install command, the
    smoke commands, and the CANDIDATE -> PRODUCTION promotion criteria."""
    assert (ROOT / ".github" / "workflows" / "release.yml").exists()
    seed = yaml.safe_load((ROOT / "seed.yaml").read_text())
    release = seed["release"]
    assert release["workflow"] == ".github/workflows/release.yml"
    assert "pip install" in release["install_command"]
    smoke = release["smoke_commands"]
    assert "alchemia --help" in smoke
    assert "alchemia status" in smoke
    promotion = release["promotion"]
    assert promotion["from"] == "CANDIDATE"
    assert promotion["to"] == "PRODUCTION"
    requires = " ".join(promotion["requires"]).lower()
    assert "tag" in requires
    assert "smoke" in requires
