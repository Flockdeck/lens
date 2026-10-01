from tests.recording.conftest import FIXTURES, load_builder


def test_committed_fixtures_match_generator() -> None:
    for name, data in load_builder().all_fixtures().items():
        assert (FIXTURES / name).read_bytes() == data, f"{name} is stale: run build.py"
