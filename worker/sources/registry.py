"""Source registry (Phase 4.1).

Sources register by unique ``source_name``; several sources may share one
``source_type`` (e.g. multiple Greenhouse boards). The pipeline reads only
from here, so adding greenhouse/lever/ashby/company_careers/search_engine
later means registering a new :class:`JobSource` — no pipeline changes.
The mock source is registered on import.
"""

from typing import Optional

from worker.sources.base import JobSource

_sources: dict = {}


def register_source(source: JobSource) -> JobSource:
    """Register (or replace) a source by its ``source_name``."""
    if not getattr(source, "source_name", ""):
        raise ValueError("source must define a non-empty source_name")
    _sources[source.source_name] = source
    return source


def get_source(name: str) -> Optional[JobSource]:
    """Return the source registered as ``name`` (None when unknown)."""
    return _sources.get(name)


def get_sources_by_type(source_type: str) -> list:
    """All registered sources of one type (e.g. all "greenhouse" boards)."""
    return [s for s in _sources.values() if s.source_type == source_type]


def get_all_sources() -> list:
    """All registered sources in registration order."""
    return list(_sources.values())


def clear_sources() -> None:
    """Remove all registrations (tests only)."""
    _sources.clear()


def _register_builtin_sources() -> None:
    """Register mock + greenhouse + lever + ashby + himalaya + jobicy (all disabled-safe: no network unless configured)."""
    from worker.sources.ashby.source import AshbySource
    from worker.sources.greenhouse.source import GreenhouseSource
    from worker.sources.himalayas.source import HimalayaSource
    from worker.sources.jobicy.source import JobicySource
    from worker.sources.lever.source import LeverSource
    from worker.sources.manual.mock_source import MockSource

    register_source(MockSource())
    register_source(GreenhouseSource())
    register_source(LeverSource())
    register_source(AshbySource())
    register_source(HimalayaSource())
    register_source(JobicySource())


_register_builtin_sources()
