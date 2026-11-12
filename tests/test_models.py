"""Source records keep independent mutable collections."""

from pubmon.models import Confidence, Lane, Source, Work, WorkType


def make_work():
    return Work(
        source=Source.ARXIV,
        source_id="2401.99999",
        lane=Lane.ARXIV_FEED,
        title="Synthetic paper",
        title_norm="synthetic paper",
        pub_date="2024-01-01",
        year=2024,
        type=WorkType.PREPRINT,
        raw_hash="synthetic",
    )


def test_work_collections_do_not_leak_between_records():
    first, second = make_work(), make_work()
    first.extra_dois.append("10.5555/example")
    first.matched_names.append("Synthetic Author")
    assert second.extra_dois == []
    assert second.matched_names == []
    assert second.confidence is Confidence.UNCERTAIN
    assert second.doi is None
