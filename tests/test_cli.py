from importlib import resources
from pathlib import Path

import pytest

from blueprint.cli import install_skill, main


PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


class TestSkillPackaging:
    """The skill ships as package data, which is easy to drop by accident.

    Running from a source checkout the markdown is on disk regardless of what
    pyproject.toml says, so resource lookups alone would not notice a dropped
    `package-data` entry — the declaration is asserted separately below.
    """

    @pytest.mark.skipif(not PYPROJECT.is_file(), reason="not a source checkout")
    def test_pyproject_declares_skill_package_data(self):
        text = PYPROJECT.read_text(encoding="utf-8")
        assert "[tool.setuptools.package-data]" in text
        assert '"blueprint.skill"' in text
        assert "SKILL.md" in text
        assert "references/*.md" in text

    @pytest.mark.skipif(not PYPROJECT.is_file(), reason="not a source checkout")
    def test_pyproject_declares_console_script(self):
        text = PYPROJECT.read_text(encoding="utf-8")
        assert "[project.scripts]" in text
        assert "blueprint.cli:main" in text

    def test_skill_files_are_importable_resources(self):
        root = resources.files("blueprint.skill")
        assert (root / "SKILL.md").is_file()
        assert (root / "references" / "gotchas.md").is_file()

    def test_skill_has_valid_frontmatter(self):
        text = (resources.files("blueprint.skill") / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        assert "name: blueprint-synth" in frontmatter
        assert "description:" in frontmatter

    def test_skill_name_matches_package(self):
        """The install destination is derived from this name, so they must agree."""
        from blueprint.cli import DEFAULT_SKILL_DIR
        assert DEFAULT_SKILL_DIR.name == "blueprint-synth"


class TestInstallSkill:
    def test_installs_into_empty_dest(self, tmp_path):
        dest = tmp_path / "blueprint-synth"
        assert install_skill(dest, force=False) == 0
        assert (dest / "SKILL.md").is_file()
        assert (dest / "references" / "gotchas.md").is_file()

    def test_refuses_existing_dest_without_force(self, tmp_path, capsys):
        dest = tmp_path / "blueprint-synth"
        dest.mkdir()
        assert install_skill(dest, force=False) == 1
        assert "--force" in capsys.readouterr().err

    def test_force_overwrites(self, tmp_path):
        dest = tmp_path / "blueprint-synth"
        dest.mkdir()
        (dest / "stale.md").write_text("old")
        assert install_skill(dest, force=True) == 0
        assert (dest / "SKILL.md").is_file()
        assert not (dest / "stale.md").exists()

    def test_copies_no_python_files(self, tmp_path):
        """__init__.py is a packaging detail and should not land in a skill dir."""
        dest = tmp_path / "blueprint-synth"
        install_skill(dest, force=False)
        assert list(dest.rglob("*.py")) == []


class TestCliEntryPoint:
    def test_install_skill_via_main(self, tmp_path):
        dest = tmp_path / "blueprint-synth"
        assert main(["install-skill", "--dest", str(dest)]) == 0
        assert (dest / "SKILL.md").is_file()

    def test_no_subcommand_exits(self):
        with pytest.raises(SystemExit):
            main([])

    def test_version_flag_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
