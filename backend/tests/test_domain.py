import pytest

from app.core.domain import AgentStatus as S
from app.core.domain import can_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [(S.DISCOVERED, S.DESIGNED), (S.DESIGNED, S.BUILT), (S.BUILT, S.TESTING),
     (S.TESTING, S.EVALUATED), (S.TESTING, S.BUILT), (S.EVALUATED, S.DEPLOYED),
     (S.DEPLOYED, S.UPGRADING), (S.UPGRADING, S.TESTING), (S.DEPLOYED, S.RETIRED)],
)  # fmt: skip
def test_allowed_transitions(current: S, target: S) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [(S.DESIGNED, S.DEPLOYED), (S.UPGRADING, S.DEPLOYED), (S.RETIRED, S.DESIGNED),
     (S.RETIRED, S.RETIRED), (S.BUILT, S.EVALUATED)],
)  # fmt: skip
def test_forbidden_transitions(current: S, target: S) -> None:
    """A new version can only reach production through testing and evaluation."""
    assert not can_transition(current, target)
