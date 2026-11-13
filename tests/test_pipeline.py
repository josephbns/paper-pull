"""End-to-end offline collection, matching, read-only reconciliation and exports."""

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

from pubmon import cli, export, pipeline
from pubmon.decisions import import_decisions
from pubmon.sources import collect as sources
from pubmon.sources.common import LaneFailed
from pubmon.store import Store

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "tests/fixtures/synthetic_master.xlsx"
FIXTURES = ROOT / "tests/fixtures/api"


def records(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_one_row_per_paper(project):
    before = hashlib.sha256(MASTER.read_bytes()).hexdigest()
    result = pipeline.run(project, master_path=MASTER, fixtures=FIXTURES, xlsx=True)
    rows = records(result["paths"]["candidates"])
    assert result["status"] == "completed" and result["papers"] == 3
    assert len(rows) == len({row["work_key"] for row in rows}) == 3
    combined = next(row for row in rows if row["doi"] == "10.5555/synthetic-1")
    assert combined["arxiv_id"] == "arXiv:2401.99999"
    assert "pair" in combined["lanes"] and "arxiv_feed" in combined["lanes"]
    assert "LINKED_PREPRINT" in combined["events"]
    workbook = load_workbook(Path(result["paths"]["candidates"]).with_suffix(".xlsx"))
    headers = [cell.value for cell in workbook.active[1]]
    assert headers == export.COLUMNS
    for row in workbook.active.iter_rows(min_row=2):
        assert row[headers.index("arxiv_id")].number_format == "@"
    workbook.close()
    assert hashlib.sha256(MASTER.read_bytes()).hexdigest() == before


def test_rerun_exports_zero_candidates_and_preserves_review_file(project):
    first = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    initial = Path(first["paths"]["candidates"])
    original = initial.read_bytes()
    second = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert second["status"] == "completed"
    assert second["candidates"] == 0
    assert first["paths"]["candidates"] != second["paths"]["candidates"]
    assert initial.read_bytes() == original
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        assert store.list_unexported_events() == []
        assert len(store.list_runs()) == 2
        assert len(store.list_works()) == 3


@pytest.mark.parametrize(
    "status, expected", [(404, "completed"), (403, "partial"), (503, "partial")]
)
def test_crossref_absence_preserves_papers_but_service_failures_stay_partial(
    project, monkeypatch, status, expected
):
    from dataclasses import replace

    import httpx2

    from pubmon.sources import crossref

    def get(url, **kwargs):
        return httpx2.Response(status, request=httpx2.Request("GET", url))

    def enrich(doi, settings, report, fixtures):
        return crossref.enrich(
            doi, replace(settings, email="synthetic@example.invalid"), report=report
        )

    monkeypatch.setattr(httpx2, "get", get)
    monkeypatch.setattr(crossref._request.retry, "sleep", lambda _: None)
    monkeypatch.setattr(sources, "enrich", enrich)
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES, xlsx=True)
    assert result["status"] == expected
    rows = records(result["paths"]["candidates"])
    assert any(row["doi"] == "10.5555/synthetic-1" for row in rows)
    assert Path(result["paths"]["candidates"]).with_suffix(".xlsx").is_file()
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        lane = json.loads(store.list_runs()[0]["counts_json"])["lanes"]["crossref"]
        if status == 404:
            assert lane["skipped"]["not_found"] > 0 and not lane["errors"]
        else:
            assert lane["status"] == "failed" and lane["errors"]


def test_dry_run_leaves_no_database_or_exports(project):
    result = pipeline.run(project, no_master=True, dry_run=True, fixtures=FIXTURES)
    assert result["candidates"] == 3 and result["paths"] == {}
    assert not (project.project_dir / "data").exists()
    assert not (project.project_dir / "demo").exists()
    assert not (project.project_dir / "demo/out").exists()


def test_dry_run_does_not_change_existing_database(project):
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    path = project.project_dir / "demo/data/pubmon.db"
    before = path.read_bytes()
    outputs = {
        file.name: file.read_bytes() for file in (project.project_dir / "demo/out").iterdir()
    }
    pipeline.run(project, no_master=True, dry_run=True, fixtures=FIXTURES)
    assert path.read_bytes() == before
    assert outputs == {
        file.name: file.read_bytes() for file in (project.project_dir / "demo/out").iterdir()
    }


def test_errata_not_new_papers(project):
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    rows = records(result["paths"]["candidates"])
    corrected = next(row for row in rows if row["doi"] == "10.5555/synthetic-1")
    assert "CORRECTION" in corrected["events"] and "RETRACTED" in corrected["events"]
    assert not any(row["doi"] in {"10.5555/synthetic-5", "10.5555/synthetic-6"} for row in rows)
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        key = corrected["work_key"]
        assert store.get_work_state(key)["is_retracted"]
        assert all(row["type"] != "dataset" for row in store.list_works())


def test_failed_export_leaves_events_pending_for_retry(project, monkeypatch):
    def fail(*args):
        raise OSError("synthetic rename failure")

    monkeypatch.setattr(export.os, "replace", fail)
    with pytest.raises(OSError, match="synthetic rename failure"):
        pipeline.run(project, no_master=True, fixtures=FIXTURES)
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        assert store.list_unexported_events()
        assert store.list_runs()[0]["status"] == "failed"
    monkeypatch.undo()
    retry = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert retry["candidates"] == 3
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        assert not store.list_unexported_events()


def test_partial_lane_failure_keeps_other_lanes(project, monkeypatch):
    original = sources._replay

    def fail_pair(lane, *args):
        if lane == "pair":
            raise LaneFailed(lane, "synthetic outage")
        return original(lane, *args)

    monkeypatch.setattr(sources, "_replay", fail_pair)
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert result["status"] == "partial" and result["papers"] == 3
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        counts = json.loads(store.list_runs()[0]["counts_json"])
        assert counts["lanes"]["pair"]["status"] == "failed"
        assert counts["lanes"]["clinic_quantum"]["status"] == "completed"


def test_rejected_not_resurfaced(project, tmp_path):
    first = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    rows = records(first["paths"]["candidates"])
    reviewed = tmp_path / "reviewed.csv"
    for row in rows:
        row["decision"] = "rejected"
    export.write_candidates(rows, reviewed)
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        counts = import_decisions(reviewed, store, decided_at="2020-01-01T00:00:00+00:00")
        assert counts["imported"] == 3
    second = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert second["candidates"] == 0
    local = tmp_path / "changed-fixtures"
    shutil.copytree(FIXTURES, local)
    crossref = json.loads((local / "crossref.json").read_text())
    crossref["message"]["container-title"] = ["A changed synthetic journal"]
    (local / "crossref.json").write_text(json.dumps(crossref))
    page = json.loads((local / "openalex.json").read_text())
    page["results"][0]["title"] += " revised"
    (local / "openalex.json").write_text(json.dumps(page))
    changed = pipeline.run(project, no_master=True, fixtures=local)
    assert changed["candidates"] == 1


def test_multiple_changes_one_row(project, tmp_path):
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    local = tmp_path / "changed-fixtures"
    shutil.copytree(FIXTURES, local)
    page = json.loads((local / "openalex.json").read_text())
    page["results"][0]["title"] += " revised"
    (local / "openalex.json").write_text(json.dumps(page))
    crossref = json.loads((local / "crossref.json").read_text())
    crossref["message"].update(
        {
            "container-title": ["New venue"],
            "published": {"date-parts": [[2026, 11, 2]]},
            "type": "proceedings-article",
        }
    )
    (local / "crossref.json").write_text(json.dumps(crossref))
    result = pipeline.run(project, no_master=True, fixtures=local)
    rows = records(result["paths"]["candidates"])
    assert len(rows) == 1
    assert all(name + ":" in rows[0]["changes"] for name in ("venue", "pub_date", "type"))


def test_cli_run_and_status_are_usable_offline(project, capsys):
    prefix = ["--project-dir", str(project.project_dir), "--profile", "cleveland-clinic"]
    assert cli.main(prefix + ["run", "--no-master", "--fixtures", str(FIXTURES)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["papers"] == 3
    assert cli.main(prefix + ["status", "--demo"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "completed"


def test_rate_limit_and_outage(project, source_settings, api_fixture, monkeypatch):
    from io import BytesIO

    import pyalex.api
    import urllib3

    from pubmon.sources import openalex

    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    original_session = pyalex.api._get_requests_session
    replay = sources._replay
    codes = iter([429, 503, 200])
    seen = []

    def session():
        client = original_session()
        client.trust_env = False  # No proxy/socket is used by the mocked connection pool.
        return client

    def response(*args, **kwargs):
        code = next(codes)
        seen.append(code)
        return urllib3.response.HTTPResponse(
            status=code,
            body=BytesIO(json.dumps(api_fixture("openalex.json")).encode()),
            preload_content=False,
        )

    def fetch(lane, settings, known, report, backfill, fixtures):
        if lane == "pair":
            return openalex.fetch_pair(source_settings, report=report)
        return replay(lane, settings, known, report, backfill, fixtures)

    monkeypatch.setattr(pyalex.api, "_get_requests_session", session)
    monkeypatch.setattr(urllib3.connectionpool.HTTPSConnectionPool, "_make_request", response)
    monkeypatch.setattr(urllib3.util.retry.Retry, "sleep", lambda *args: None)
    monkeypatch.setattr(sources, "_replay", fetch)
    assert pipeline.run(project, no_master=True, fixtures=FIXTURES)["status"] == "completed"
    assert seen == [429, 503, 200]
    codes = iter([503] * 4)
    seen.clear()
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert result["status"] == "partial" and seen == [503] * 4
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        assert len(store.list_works()) == 3
        assert not any(
            event["kind"] == "DELETED"
            for work in store.list_works()
            for event in store.list_events(work["work_key"])
        )


def test_unchanged_notices_are_not_fetched_again(project, monkeypatch):
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    original = sources.enrich
    requested = []

    def counted(doi, *args):
        requested.append(doi)
        return original(doi, *args)

    monkeypatch.setattr(sources, "enrich", counted)
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert "10.5555/synthetic-5" not in requested
    assert "10.5555/synthetic-6" not in requested


def test_matching_interruption_leaves_prior_papers_and_marks_failed_run(project, monkeypatch):
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        before = store.list_works()
    original = pipeline.resolve_and_store

    def interrupted(works, *args, **kwargs):
        def failing():
            yield works[0]
            raise RuntimeError("synthetic interrupted matching")

        return original(failing(), *args, **kwargs)

    monkeypatch.setattr(pipeline, "resolve_and_store", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interrupted matching"):
        pipeline.run(project, no_master=True, fixtures=FIXTURES)
    with Store(project.project_dir / "demo/data/pubmon.db") as store:
        assert store.list_works() == before
        assert store.list_runs()[0]["status"] == "failed"


def test_demo_replay_never_creates_live_history(project, capsys):
    pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert (project.project_dir / "demo/data/pubmon.db").exists()
    assert not (project.project_dir / "data").exists()
    assert not (project.project_dir / "out").exists()
    assert (
        cli.main(
            ["--project-dir", str(project.project_dir), "--profile", "cleveland-clinic", "status"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []


def test_malformed_failed_lane_still_allows_other_sources(project, monkeypatch):
    original = sources._replay

    def malformed(lane, settings, known, report, backfill, fixtures):
        if lane == "pair":
            report.raw_records.append({"malformed_synthetic_response": True})
            raise LaneFailed(lane, "Missing record identity")
        return original(lane, settings, known, report, backfill, fixtures)

    monkeypatch.setattr(sources, "_replay", malformed)
    result = pipeline.run(project, no_master=True, fixtures=FIXTURES)
    assert result["status"] == "partial" and result["papers"] == 3


def test_custom_partner_workspaces_keep_history_and_cli_separate(project, capsys):
    from dataclasses import replace

    first = replace(
        project,
        collaboration_name="Synthetic QIC A",
        partner_label="QIC A",
        workspace_dir=project.project_dir / "workspaces/a",
    )
    second = replace(
        project,
        collaboration_name="Synthetic QIC B",
        partner_label="QIC B",
        workspace_dir=project.project_dir / "workspaces/b",
    )
    one = pipeline.run(first, no_master=True, fixtures=FIXTURES)
    two = pipeline.run(second, no_master=True, fixtures=FIXTURES)
    assert one["collaboration"] == "Synthetic QIC A" and two["partner"] == "QIC B"
    assert one["candidates"] == two["candidates"] == 3
    assert (project.project_dir / "workspaces/a/demo/data/pubmon.db").exists()
    assert (project.project_dir / "workspaces/b/demo/data/pubmon.db").exists()
    assert not (project.project_dir / "demo").exists()
    assert pipeline.run(first, no_master=True, fixtures=FIXTURES)["candidates"] == 0
    local = project.project_dir / "config/settings.toml"
    template = (project.project_dir / "config/settings.example.toml").read_text()
    local.write_text(template.replace('workspace = "."', 'workspace = "workspaces/a"'))
    assert cli.main(["--project-dir", str(project.project_dir), "status", "--demo"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
