"""Cliente mínimo de PostgREST (Supabase) con la service role.

Los filtros se pasan tal cual los entiende PostgREST: {"status": "eq.new", "or": "(a.is.null,a.lt.2026-01-01)"}.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DBError(Exception):
    pass


class DB:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        url = url or os.environ.get("SUPABASE_URL", "")
        key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            raise DBError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
        self.base = url.rstrip("/") + "/rest/v1"
        self.session = requests.Session()
        # Mientras se espera a LinkedIn (por el proxy) la conexión a Supabase se queda muerta y la
        # siguiente petición se colgaba 30 s. Se reintenta con una conexión nueva y menos espera.
        retry = Retry(total=3, connect=3, read=2, status=2, backoff_factor=0.5,
                      status_forcelist=(502, 503, 504), allowed_methods=None, raise_on_status=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({"apikey": key, "Content-Type": "application/json"})
        # Las claves nuevas (sb_secret_...) no son JWT: sólo van en apikey.
        if key.startswith("eyJ"):
            self.session.headers["Authorization"] = f"Bearer {key}"

    def _check(self, res: requests.Response) -> Any:
        if res.status_code >= 300:
            raise DBError(f"{res.status_code} {res.text[:500]}")
        if not res.content:
            return None
        return res.json()

    def select(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
        columns: str = "*",
    ) -> List[Dict]:
        params: Dict[str, Any] = {"select": columns, **(filters or {})}
        if order:
            params["order"] = order
        if limit:
            params["limit"] = limit
        return self._check(self.session.get(f"{self.base}/{table}", params=params, timeout=(5, 15))) or []

    def one(self, table: str, filters: Dict[str, Any], columns: str = "*") -> Optional[Dict]:
        rows = self.select(table, filters, limit=1, columns=columns)
        return rows[0] if rows else None

    def count(self, table: str, filters: Optional[Dict[str, Any]] = None) -> int:
        params = {"select": "id", **(filters or {})}
        res = self.session.head(
            f"{self.base}/{table}",
            params=params,
            headers={"Prefer": "count=exact", "Range": "0-0"},
            timeout=(5, 15),
        )
        if res.status_code >= 300:
            raise DBError(f"{res.status_code} count {table}")
        total = res.headers.get("content-range", "*/0").split("/")[-1]
        return int(total) if total.isdigit() else 0

    def insert(
        self,
        table: str,
        rows: Any,
        on_conflict: Optional[str] = None,
        ignore_duplicates: bool = False,
    ) -> List[Dict]:
        prefer = ["return=representation"]
        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
            prefer.append("resolution=ignore-duplicates" if ignore_duplicates else "resolution=merge-duplicates")
        res = self.session.post(
            f"{self.base}/{table}",
            params=params,
            json=rows,
            headers={"Prefer": ",".join(prefer)},
            timeout=(5, 15),
        )
        return self._check(res) or []

    def update(self, table: str, filters: Dict[str, Any], values: Dict[str, Any]) -> List[Dict]:
        if not filters:
            raise DBError("update sin filtros")
        if table in ("sdr_leads", "sdr_campaigns", "sdr_settings"):
            values = {**values, "updated_at": now_iso()}
        res = self.session.patch(
            f"{self.base}/{table}",
            params=filters,
            json=values,
            headers={"Prefer": "return=representation"},
            timeout=(5, 15),
        )
        return self._check(res) or []
