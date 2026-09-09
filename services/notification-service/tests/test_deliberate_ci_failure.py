"""Deliberate, throwaway failure — proves the branch-protection merge gate
actually blocks a red CI, not just reports it. Removed once verified;
never meant to land on main."""


def test_deliberate_failure_for_ci_negative_path_check():
    assert False, "Intentional failure to verify CI Result blocks the merge button"
