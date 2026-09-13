import os

from immanuel.hack import thinking


def test_brains_present():
    paths = thinking.brain_paths()
    names = {os.path.basename(p) for p in paths}
    # all five pattern-forge brains vendored into the package
    assert "PatternForge-SKILL.md" in names
    assert "shepherd-mass-elite-grade-system.txt" in names
    assert len(paths) == 5


def test_load_brains_nonempty():
    brains = thinking.load_brains()
    assert brains
    assert any(len(v) > 1000 for v in brains.values())


def test_compose_instruction_has_framework_and_user():
    text = thinking.compose_instruction("focus on IDOR and auth")
    low = text.lower()
    assert "pattern forge" in low
    assert "universal debugger" in low or "expected_model" in low
    assert "focus on idor and auth" in low
    assert "operator instruction" in low


def test_compose_without_arch_is_just_user():
    text = thinking.compose_instruction("only check headers", include_arch=False)
    assert text.strip() == "operator instruction for this run:\nonly check headers"


def test_workspace_file_specs_map_into_sandbox():
    specs = thinking.workspace_file_specs()
    assert len(specs) == 5
    for s in specs:
        # rpartition: DEST has no colon; the Windows drive colon stays in src
        src, _, dest = s.rpartition(":")
        assert os.path.isfile(src)
        assert dest.startswith("skills/patternforge/")
