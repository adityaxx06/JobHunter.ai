"""Company repository (Phase 3). Upserts key on UNIQUE(normalized_name)."""

from typing import Optional

from app.db import connection as db

_COMPANY_COLS = (
    "id, name, normalized_name, website_url, careers_url, "
    "logo_url, description, domain, created_at, updated_at"
)


def get_company(company_id: str) -> Optional[dict]:
    """Fetch one company by id (None when not found)."""
    return db.fetch_one(
        f"SELECT {_COMPANY_COLS} FROM public.companies WHERE id = %s",
        (company_id,),
    )


def find_company_by_normalized_name(normalized_name: str) -> Optional[dict]:
    """Fetch one company by its dedup key (None when not found)."""
    return db.fetch_one(
        f"SELECT {_COMPANY_COLS} FROM public.companies WHERE normalized_name = %s",
        (normalized_name,),
    )


def create_company(
    name: str,
    normalized_name: str,
    website_url: Optional[str] = None,
    careers_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    description: Optional[str] = None,
    domain: Optional[str] = None,
) -> Optional[dict]:
    """Insert a company and return the new row."""
    return db.execute(
        """INSERT INTO public.companies
           (name, normalized_name, website_url, careers_url, logo_url, description, domain)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id, name, normalized_name, website_url, careers_url,
                     logo_url, description, domain, created_at, updated_at""",
        (name, normalized_name, website_url, careers_url, logo_url, description, domain),
    )


def upsert_company(
    name: str,
    normalized_name: str,
    website_url: Optional[str] = None,
    careers_url: Optional[str] = None,
    logo_url: Optional[str] = None,
    description: Optional[str] = None,
    domain: Optional[str] = None,
) -> Optional[dict]:
    """Insert or (on normalized_name conflict) refresh mutable fields."""
    return db.execute(
        """INSERT INTO public.companies
           (name, normalized_name, website_url, careers_url, logo_url, description, domain)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (normalized_name) DO UPDATE SET
             name = EXCLUDED.name,
             website_url = COALESCE(EXCLUDED.website_url, public.companies.website_url),
             careers_url = COALESCE(EXCLUDED.careers_url, public.companies.careers_url),
             logo_url = COALESCE(EXCLUDED.logo_url, public.companies.logo_url),
             description = COALESCE(EXCLUDED.description, public.companies.description),
             domain = COALESCE(EXCLUDED.domain, public.companies.domain)
           RETURNING id, name, normalized_name, website_url, careers_url,
                     logo_url, description, domain, created_at, updated_at""",
        (name, normalized_name, website_url, careers_url, logo_url, description, domain),
    )
