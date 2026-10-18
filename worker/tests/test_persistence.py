"""Phase 5.1 persistence tests. Fully offline via an in-memory FakeDB.

FakeDB speaks the same protocol as worker.db.client (is_configured,
transaction() yielding a cursor with execute/fetchone/fetchall) and
interprets the repository's parameterized SQL against dict stores — no live
database, no network. Repository code is exercised through
mock.patch.object(job_repository.db, ...) — wait, FakeDB replaces the whole
module attribute instead (same seam, less brittle).
"""

import copy
import json
from contextlib import contextmanager

import pytest

from worker.db import job_repository as repo
from worker.models.job import DiscoveredJob
from worker.processors.normalizer.job_normalizer import normalize_job
from worker.sources.manual.mock_source import MockSource

_JOB_INSERT_COLS = (
    "company_id", "title", "normalized_title", "description", "location",
    "is_remote", "employment_type", "experience_level", "salary_min",
    "salary_max", "salary_currency", "skills", "posted_at",
    "canonical_url", "apply_url",
)


class FakeTx:
    """Cursor stand-in dispatching parameterized SQL to in-memory stores."""

    def __init__(self, store, fail_on=None) -> None:
        self.store = store
        self.fail_on = fail_on or set()
        self._result = None

    # -- protocol ---------------------------------------------------------
    def execute(self, sql, params=()):
        self._result = None
        self._dispatch(sql, tuple(params or ()))

    def fetchone(self):
        return copy.deepcopy(self._result[0]) if self._result else None

    def fetchall(self):
        return copy.deepcopy(self._result or [])

    # -- dispatch ----------------------------------------------------------
    def _dispatch(self, sql, params):
        s = self.store
        if "FROM public.companies WHERE normalized_name" in sql:
            row = s["companies"].get(params[0])
            self._result = [row] if row else []
        elif "INSERT INTO public.companies" in sql:
            if "companies" in self.fail_on:
                raise RuntimeError("simulated company insert failure")
            s["seq"]["c"] += 1
            row = {"id": f"c{s['seq']['c']}", "name": params[0],
                   "normalized_name": params[1], "domain": params[2]}
            s["companies"][params[1]] = row
            self._result = [row]
        elif "j.apply_url = %s" in sql:
            row = next((j for j in s["jobs"].values() if j.get("apply_url") == params[0]), None)
            self._result = [row] if row else []
        elif "FROM public.jobs" in sql and "normalized_title" in sql:
            rows = [j for j in s["jobs"].values() if j.get("normalized_title") == params[0]]
            self._result = rows[: params[1]]
        elif "INSERT INTO public.jobs" in sql:
            if "jobs" in self.fail_on:
                raise RuntimeError("simulated job insert failure")
            if "FAIL" in str(params[1]):
                raise RuntimeError("simulated per-job failure")
            s["seq"]["j"] += 1
            row = {"id": f"j{s['seq']['j']}", "first_seen_at": "now", "last_seen_at": "now"}
            row.update(dict(zip(_JOB_INSERT_COLS, params)))
            row["skills"] = json.loads(row["skills"]) if isinstance(row["skills"], str) else row["skills"]
            s["jobs"][row["id"]] = row
            self._result = [{"id": row["id"], "company_id": row["company_id"],
                             "title": row["title"], "normalized_title": row["normalized_title"]}]
        elif sql.strip().startswith("UPDATE public.jobs SET last_seen_at"):
            s["jobs"][params[0]]["last_seen_at"] = "later"
            self._result = [{"id": params[0]}]
        elif sql.strip().startswith("UPDATE public.jobs SET"):
            if "jobs" in self.fail_on:
                raise RuntimeError("simulated job update failure")
            set_part = sql.split("SET", 1)[1].split("WHERE")[0]
            cols = [c.split("=")[0].strip() for c in set_part.split(",") if "=" in c and "last_seen_at" not in c]
            row = s["jobs"][params[-1]]
            for col, value in zip(cols, params[:-1]):
                row[col] = json.loads(value) if col == "skills" and isinstance(value, str) else value
            row["last_seen_at"] = "later"
            self._result = [{"id": row["id"], "company_id": row.get("company_id"),
                             "title": row.get("title"), "normalized_title": row.get("normalized_title")}]
        elif "FROM public.job_sources" in sql:
            job_id, stype, sname, ext = params
            row = next((r for r in s["sources"]
                        if r["job_id"] == job_id and r["source_type"] == stype
                        and r["source_name"] == sname and r["source_job_id"] == ext), None)
            self._result = [row] if row else []
        elif "INSERT INTO public.job_sources" in sql:
            if "job_sources" in self.fail_on:
                raise RuntimeError("simulated source-link failure")
            s["seq"]["s"] += 1
            row = {"id": f"s{s['seq']['s']}", "job_id": params[0], "source_type": params[1],
                   "source_name": params[2], "source_url": params[3], "apply_url": params[4],
                   "source_job_id": params[5], "metadata": json.loads(params[6])}
            s["sources"].append(row)
            self._result = [{"id": row["id"]}]
        else:  # pragma: no cover - unknown statement surfaces loudly
            raise AssertionError(f"FakeDB cannot handle SQL: {sql[:80]}")


class FakeDB:
    """Module-attribute replacement for worker.db.client in tests."""

    def __init__(self, configured=True, fail_on=None) -> None:
        self.configured = configured
        self.fail_on = fail_on or set()
        self.stores = {"companies": {}, "jobs": {}, "sources": [],
                       "seq": {"c": 0, "j": 0, "s": 0}}
        self.snapshots = []
        self.executed = []  # (sql, params) log for parameterization assertions

    def is_configured(self):
        return self.configured

    @contextmanager
    def transaction(self):
        self.snapshots.append(copy.deepcopy(self.stores))
        tx = FakeTx(self.stores, self.fail_on)
        recording = tx

        original_execute = tx.execute

        def execute(sql, params=()):
            self.executed.append((sql, tuple(params or ())))
            return original_execute(sql, params)

        tx.execute = execute
        try:
            yield tx
        except Exception:
            self.stores = self.snapshots.pop()  # rollback
            raise
        self.snapshots.pop()  # commit


@pytest.fixture
def fakedb(monkeypatch):
    """Install FakeDB as job_repository.db and return it."""
    fake = FakeDB()
    monkeypatch.setattr(repo, "db", fake)
    return fake


def _job(**overrides):
    base = {
        "external_id": "e1",
        "title": "Java Developer Intern",
        "company_name": "Example Technologies",
        "company_domain": "",
        "location": "Chennai, India",
        "employment_type": "Internship",
        "description": "Full job description",
        "skills": ["Java", "SQL"],
        "source_type": "greenhouse",
        "source_name": "greenhouse:example",
        "source_url": "https://boards.greenhouse.io/example",
        "apply_url": "https://boards.greenhouse.io/example/jobs/1",
    }
    base.update(overrides)
    return normalize_job(DiscoveredJob(**base))


# --- 1. new job insertion (incl. quoting-safe parameterization) -----------------


def test_new_job_insertion(fakedb):
    outcome = repo.persist_job(_job(title="O'Brien Developer Intern"))
    assert outcome["action"] == "inserted" and outcome["job_id"]
    assert outcome["company_created"] is True and outcome["source_link_created"] is True
    assert len(fakedb.stores["jobs"]) == 1 and len(fakedb.stores["companies"]) == 1
    sql_text = " ".join(sql for sql, _ in fakedb.executed)
    assert "O'Brien" not in sql_text  # values travel as params, never inline
    assert all("%s" in sql for sql, _ in fakedb.executed)


# --- 2/3. existing job + duplicate fingerprint -------------------------------------


def test_existing_job_detected_and_duplicate_fingerprint(fakedb):
    first = repo.persist_job(_job())
    second = repo.persist_job(_job(external_id="e2"))  # different ext id, same fingerprint
    assert first["job_id"] == second["job_id"]
    assert second["action"] == "duplicate"
    assert len(fakedb.stores["jobs"]) == 1


# --- 4. same job from different sources ----------------------------------------------


def test_same_job_from_different_sources(fakedb):
    first = repo.persist_job(_job())
    other = _job(source_type="lever", source_name="lever:example",
                 source_url="https://jobs.lever.co/example",
                 external_id="L9")  # same title/company/location/apply URL
    second = repo.persist_job(other)
    assert second["job_id"] == first["job_id"] and second["action"] == "duplicate"
    assert len(fakedb.stores["jobs"]) == 1 and len(fakedb.stores["sources"]) == 2


# --- 5/6. location / apply-URL differences stay separate ---------------------------------


def test_different_location_remains_separate(fakedb):
    repo.persist_job(_job())
    other = repo.persist_job(_job(location="Mumbai, India",
                                  apply_url="https://boards.greenhouse.io/example/jobs/2"))
    assert other["action"] == "inserted" and len(fakedb.stores["jobs"]) == 2


def test_different_apply_url_remains_separate(fakedb):
    repo.persist_job(_job())
    other = repo.persist_job(_job(apply_url="https://boards.greenhouse.io/example/jobs/9"))
    assert other["action"] == "inserted" and len(fakedb.stores["jobs"]) == 2


# --- 7/8/9/10. company + source-link accounting ----------------------------------------------


def test_company_reuse_and_creation_counts(fakedb):
    repo.persist_job(_job())
    assert fakedb.stores["companies"].keys() == {"example"}
    repo.persist_job(_job(title="Python Developer Intern",
                          apply_url="https://boards.greenhouse.io/example/jobs/3"))
    assert len(fakedb.stores["companies"]) == 1  # reused, not duplicated


def test_source_link_created_once(fakedb):
    repo.persist_job(_job())
    assert len(fakedb.stores["sources"]) == 1
    repo.persist_job(_job())  # same source association
    assert len(fakedb.stores["sources"]) == 1


# --- 11/16. idempotent second run + mixed counts ----------------------------------------------


def test_idempotent_second_run(fakedb):
    from worker.models.job import DiscoveryResult

    jobs = [_job(), _job(title="Python Developer Intern",
                         apply_url="https://boards.greenhouse.io/example/jobs/3")]
    first = repo.persist_discovery_result(DiscoveryResult(jobs=jobs))
    assert (first.inserted_count, first.duplicate_count) == (2, 0)
    assert (first.companies_created, first.source_links_created) == (1, 2)
    second = repo.persist_discovery_result(DiscoveryResult(jobs=jobs))
    assert second.discovered_count == 2
    assert (second.inserted_count, second.updated_count, second.duplicate_count) == (0, 0, 2)
    assert (second.source_links_created, second.companies_created) == (0, 0)
    assert second.errors == []


# --- 12/13. updates fill blanks only ----------------------------------------------------------------


def test_update_improves_and_blanks_do_not_overwrite(fakedb):
    repo.persist_job(_job(description=""))
    improved = repo.persist_job(_job(description="Full job description"))
    assert improved["action"] == "updated"
    job = fakedb.stores["jobs"][improved["job_id"]]
    assert job["description"] == "Full job description"
    blank = repo.persist_job(_job(description="", location=""))
    assert blank["action"] == "duplicate"
    assert fakedb.stores["jobs"][blank["job_id"]]["description"] == "Full job description"


# --- 14. transaction rollback --------------------------------------------------------------------------------


def test_transaction_rollback_leaves_no_orphans():
    fake = FakeDB(fail_on={"job_sources"})
    import unittest.mock as mock

    with mock.patch.object(repo, "db", fake):
        with pytest.raises(RuntimeError):
            repo.persist_job(_job())
    assert fake.stores["jobs"] == {} and fake.stores["companies"] == {} and fake.stores["sources"] == []


# --- 15. partial job failure ------------------------------------------------------------------------------------------


def test_partial_job_failure(fakedb):
    from worker.models.job import DiscoveryResult

    jobs = [_job(), _job(title="FAIL Broken Job",
                          apply_url="https://boards.greenhouse.io/example/jobs/99"),
            _job(title="Python Developer Intern",
                 apply_url="https://boards.greenhouse.io/example/jobs/3")]
    result = repo.persist_discovery_result(DiscoveryResult(jobs=jobs))
    assert result.inserted_count == 2 and len(result.errors) == 1
    assert len(fakedb.stores["jobs"]) == 2


# --- 17. database-not-configured ----------------------------------------------------------------------------------


def test_database_not_configured():
    from worker.models.job import DiscoveryResult

    fake = FakeDB(configured=False)
    import unittest.mock as mock

    with mock.patch.object(repo, "db", fake):
        result = repo.persist_discovery_result(DiscoveryResult(jobs=[_job()]))
    assert result.inserted_count == 0 and result.discovered_count == 1
    assert any("not configured" in e for e in result.errors)


# --- 18. mock persistence protection --------------------------------------------------------------------------------------


def test_mock_persistence_protection(fakedb):
    from worker.models.job import DiscoveryResult
    from worker.processors.normalizer.job_normalizer import normalize_jobs

    mocks = normalize_jobs(MockSource().discover_jobs())
    skipped = repo.persist_discovery_result(DiscoveryResult(jobs=mocks))
    assert skipped.skipped_count == 5 and skipped.inserted_count == 0
    assert fakedb.stores["jobs"] == {}
    allowed = repo.persist_discovery_result(DiscoveryResult(jobs=mocks), allow_mock=True)
    assert allowed.inserted_count == 5
