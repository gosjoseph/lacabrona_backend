from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core.utils import (
    normalize_email,
    normalize_phone,
    strip_mongo_id,
    utcnow,
)
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schema import CustomerCreate, CustomerUpdate

# Re-exported for backwards compatibility: callers/tests import `normalize_phone`
# from this module. The canonical implementation now lives in `app.core.utils`
# so the repository can share it without a circular import.
__all__ = ["CustomerService", "normalize_email", "normalize_phone"]


def _display_name(name: Optional[str], profile: dict | None, email: Optional[str]) -> str:
    """Pick the best display `name` for a canonical customer row.

    Precedence: an explicit name, then the profile's full name, then
    "first last", then the email local-part, then "".
    """
    if name and str(name).strip():
        return str(name).strip()
    profile = profile or {}
    full = (profile.get("full_name") or "").strip()
    if full:
        return full
    parts = " ".join(
        str(p).strip()
        for p in (profile.get("first_name"), profile.get("last_name"))
        if p
    ).strip()
    if parts:
        return parts
    if email:
        return str(email).split("@", 1)[0]
    return ""


def _is_blank(value) -> bool:
    """A field counts as empty for field-union purposes."""
    return value in (None, "", [], {})


def _distinct_stids(a: dict, b: dict) -> bool:
    """True iff both records carry a supertokens id and the two ids DIFFER.

    This is the "two distinct accounts" signal: an email collision between two
    such records is a hard conflict (409), and a phone collision is a legitimate
    shared phone (never a merge).
    """
    sa = a.get("supertokens_user_id")
    sb = b.get("supertokens_user_id")
    return bool(sa) and bool(sb) and sa != sb


def _as_utc(dt):
    """Coerce a datetime to UTC-aware so created-at values can be compared even
    when one side came back naive from Mongo and the other is freshly minted."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _customer_seq(doc: dict) -> int:
    """Numeric suffix of a `cust-NNNN` id (a large sentinel when unparseable),
    so the lower/older id can be picked as the merge survivor."""
    try:
        return int(str(doc.get("id", "")).split("-")[-1])
    except Exception:
        return 1 << 62


class CustomerService:
    def __init__(self, repository: CustomerRepository):
        self.repository = repository

    # ----- directory CRUD ----------------------------------------------

    def list_customers(self, q: str | None = None) -> dict:
        return {"customers": self.repository.list(q)}

    def get_customer(self, customer_id: str) -> dict:
        doc = self.repository.find_by_id(customer_id)
        if not doc:
            raise HTTPException(404, "Customer not found")
        return doc

    def create_customer(self, body: CustomerCreate) -> dict:
        now = utcnow()
        # Insert a base row first WITHOUT the indexed identity fields, then let
        # `resolve_identity` commit the email/phone (or converge with a sharer).
        # Inserting the email separately means a colliding email never trips the
        # sparse-unique index — the collision is detected and merged instead.
        doc = {
            "id": self._next_customer_id(),
            "name": body.name,
            "notes": body.notes or "",
            "is_active": True,
            "created": now,
            "updated": now,
        }
        self.repository.insert(doc)

        target = dict(doc)
        has_identity = False
        if body.email:
            target["email"] = body.email
            email_norm = normalize_email(body.email)
            if email_norm:
                target["email_normalized"] = email_norm
                has_identity = True
        if body.phone:
            target["phone"] = body.phone
            phone_norm = normalize_phone(body.phone)
            if phone_norm:
                target["phone_normalized"] = phone_norm
                has_identity = True

        if not has_identity:
            # A name-only (or non-normalizable email/phone) row: persist any raw
            # display value and skip convergence entirely.
            if "email" in target or "phone" in target:
                return self._persist_target(target)
            return strip_mongo_id(target)
        return self.resolve_identity(target)

    def create_name_only(self, name: str) -> dict:
        """Create a canonical customer with only a display name set.

        Used when a manual order names an unknown customer: everything except
        `name` (and timestamps/flags) is left empty, and no phone fields are
        written so the sparse phone index is never touched.
        """
        now = utcnow()
        doc = {
            "id": self._next_customer_id(),
            "name": (name or "").strip(),
            "notes": "",
            "is_active": True,
            "created": now,
            "updated": now,
        }
        self.repository.insert(doc)
        return strip_mongo_id(doc)

    def update_customer(self, customer_id: str, body: CustomerUpdate) -> dict:
        existing = self.repository.find_by_id(customer_id)
        if not existing:
            raise HTTPException(404, "Customer not found")

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return existing

        identity_touched = "email" in updates or "phone" in updates
        if not identity_touched:
            # name/notes only — no email/phone collision is possible, so commit
            # directly without running convergence.
            patch = {k: v for k, v in updates.items()}
            patch["updated"] = utcnow()
            self.repository.update(customer_id, patch)
            return self.get_customer(customer_id)

        # An email/phone change may converge with another record. Build the
        # DESIRED state but commit nothing yet, so an email-conflict 409 leaves
        # both records untouched; `resolve_identity` performs every write.
        target = dict(existing)
        if "name" in updates:
            target["name"] = updates["name"]
        if "notes" in updates:
            target["notes"] = updates["notes"]
        if "email" in updates:
            target["email"] = updates["email"]
            target["email_normalized"] = normalize_email(updates["email"])
        if "phone" in updates:
            target["phone"] = updates["phone"]
            target["phone_normalized"] = normalize_phone(updates["phone"])
        target["updated"] = utcnow()
        return self.resolve_identity(target)

    def delete_customer(self, customer_id: str) -> None:
        if not self.repository.delete(customer_id):
            raise HTTPException(404, "Customer not found")

    # ----- identity convergence (merge / shared phone) ------------------

    # Fields combined on a merge: the survivor's non-empty value is kept; a
    # blank/missing survivor field takes the loser's value.
    _UNION_KEYS = (
        "name",
        "phone",
        "phone_normalized",
        "email",
        "email_normalized",
        "notes",
        "supertokens_user_id",
        "shared_phone",
        "shared_phone_with",
    )

    def resolve_identity(self, target: dict) -> dict:
        """Converge `target` with any record that shares its email or phone.

        `target` is the DESIRED state of an already-persisted customer row (it
        carries `id`, and `email_normalized`/`phone_normalized` hold the values
        being written). Its email/phone need NOT be committed yet —
        `resolve_identity` performs every write, so a colliding email never
        trips the sparse-unique index.

        Rules (email first, then phone):
          1. Email collision with another record B:
             - both have a DIFFERENT supertokens_user_id -> 409, no change.
             - else -> MERGE.
          2. Phone collision with another record B:
             - both have a DIFFERENT supertokens_user_id -> SHARED PHONE
               (flag + cross-link both, no merge).
             - else -> MERGE.
          3. No collision -> commit the desired email/phone normally.

        Returns the surviving customer doc.
        """
        target_id = target["id"]
        email_norm = target.get("email_normalized") or ""
        phone_norm = target.get("phone_normalized") or ""

        # 1. EMAIL collision.
        if email_norm:
            other = self.repository.find_other_by_email_normalized(
                email_norm, target_id
            )
            if other is not None:
                if _distinct_stids(target, other):
                    raise HTTPException(
                        409,
                        "Conflicto: dos cuentas distintas comparten este email",
                    )
                return self._merge(target, other)

        # 2. PHONE collision.
        if phone_norm:
            others = self.repository.find_others_by_phone_normalized(
                phone_norm, target_id
            )
            if others:
                # A record that is NOT a distinct-account sharer must merge.
                mergeable = next(
                    (o for o in others if not _distinct_stids(target, o)), None
                )
                if mergeable is not None:
                    return self._merge(target, mergeable)
                # Every other holder is a distinct account: shared phone.
                return self._mark_shared(target, others)

        # 3. No collision — commit the desired identity fields.
        return self._persist_target(target)

    def _merge(self, target: dict, other: dict) -> dict:
        """Merge two records into one survivor; never merge a record into itself."""
        if target["id"] == other["id"]:
            return self._persist_target(target)

        survivor, loser = self._pick_survivor(target, other)
        survivor_id = survivor["id"]
        loser_id = loser["id"]

        merged = self._union_fields(survivor, loser)
        merged["id"] = survivor_id

        # Re-point references BEFORE deleting the loser, then delete the loser
        # FIRST so its email frees the unique index before the survivor (which
        # may now hold that same email) is committed.
        self.repository.repoint_orders(loser_id, survivor_id)
        self.repository.delete(loser_id)
        return self._persist_target(merged)

    def _mark_shared(self, target: dict, others: list[dict]) -> dict:
        """Flag a legitimately shared phone and cross-link every sharer.

        Commits the target's desired phone, then unions the `shared_phone_with`
        list across the whole group so it is idempotent and supports >2 sharers.
        """
        self._persist_target(target)
        group = {o["id"] for o in others} | {target["id"]}
        for member_id in group:
            current = self.repository.find_by_id(member_id)
            if current is None:
                continue
            links = set(current.get("shared_phone_with") or []) | (
                group - {member_id}
            )
            self.repository.update(
                member_id,
                {"shared_phone": True, "shared_phone_with": sorted(links)},
            )
        return self.repository.find_by_id(target["id"])

    def _pick_survivor(self, a: dict, b: dict) -> tuple[dict, dict]:
        """Choose (survivor, loser): the record with a supertokens id wins; if
        neither has one, the OLDER record (earlier `created`, else lower
        cust-NNNN) survives."""
        a_auth = bool(a.get("supertokens_user_id"))
        b_auth = bool(b.get("supertokens_user_id"))
        if a_auth and not b_auth:
            return a, b
        if b_auth and not a_auth:
            return b, a
        return (a, b) if self._is_older_or_equal(a, b) else (b, a)

    def _is_older_or_equal(self, a: dict, b: dict) -> bool:
        ca, cb = _as_utc(a.get("created")), _as_utc(b.get("created"))
        if ca and cb and ca != cb:
            return ca < cb
        return _customer_seq(a) <= _customer_seq(b)

    def _union_fields(self, survivor: dict, loser: dict) -> dict:
        merged = dict(survivor)
        for key in self._UNION_KEYS:
            if _is_blank(survivor.get(key)) and not _is_blank(loser.get(key)):
                merged[key] = loser.get(key)
        return merged

    def _persist_target(self, target: dict) -> dict:
        """Commit a record's mutable fields, returning the stored doc.

        Identity fields use set/unset so `email_normalized` is never stored as
        an empty string (which would collide under the sparse-unique index).
        `created` is never touched, so a fresh row keeps created == updated.
        """
        cid = target["id"]
        patch: dict = {}
        unset: list[str] = []
        for key in (
            "name",
            "notes",
            "updated",
            "supertokens_user_id",
            "shared_phone",
            "shared_phone_with",
        ):
            if key in target:
                patch[key] = target[key]
        if "email" in target or "email_normalized" in target:
            patch["email"] = target.get("email")
            email_norm = target.get("email_normalized") or ""
            if email_norm:
                patch["email_normalized"] = email_norm
            else:
                unset.append("email_normalized")
        if "phone" in target or "phone_normalized" in target:
            patch["phone"] = target.get("phone")
            phone_norm = target.get("phone_normalized") or ""
            if phone_norm:
                patch["phone_normalized"] = phone_norm
            else:
                unset.append("phone_normalized")
        self.repository.update(cid, patch, unset=unset or None)
        return self.repository.find_by_id(cid)

    # ----- upsert + backfill -------------------------------------------

    def upsert(
        self, name: str, phone: str, email: Optional[str] = None
    ) -> Optional[dict]:
        phone_norm = normalize_phone(phone)
        if not phone_norm:
            return None
        existing = self.repository.find_by_phone_normalized(phone_norm)
        now = utcnow()
        if existing:
            patch: dict = {"updated": now}
            if existing.get("name") != name:
                patch["name"] = name
            if email and not existing.get("email"):
                patch["email"] = email
                # Only index a real address — an empty `email_normalized` would
                # collide under the sparse-unique email index.
                email_norm = normalize_email(email)
                if email_norm:
                    patch["email_normalized"] = email_norm
            self.repository.update(existing["id"], patch)
            return self.repository.find_by_id(existing["id"])
        doc = {
            "id": self._next_customer_id(),
            "name": name,
            "phone": phone,
            "phone_normalized": phone_norm,
            "notes": "",
            "is_active": True,
            "created": now,
            "updated": now,
        }
        if email:
            doc["email"] = email
            email_norm = normalize_email(email)
            if email_norm:
                doc["email_normalized"] = email_norm
        self.repository.insert(doc)
        return strip_mongo_id(doc)

    def backfill(self) -> dict:
        db = self.repository.collection.database
        scanned = 0
        created = 0
        updated = 0

        def _process(name: str, phone: str) -> None:
            nonlocal scanned, created, updated
            if not phone:
                return
            phone_norm = normalize_phone(phone)
            if not phone_norm:
                return
            scanned += 1
            existing = self.repository.find_by_phone_normalized(phone_norm)
            if existing is None:
                self.upsert(name=name, phone=phone)
                created += 1
            else:
                old_name = existing.get("name")
                self.upsert(name=name, phone=phone)
                if old_name != name:
                    updated += 1

        for r in db.reservations.find({}):
            _process(r.get("name", ""), r.get("phone", ""))
        for o in db.orders.find({}):
            _process(o.get("customer", ""), o.get("phone", ""))

        # Canonicalize every customer row. Legacy auth rows (no `cust-NNNN` id)
        # get one plus a derived name/email_normalized/timestamps. Each row
        # examined counts toward `scanned`; each one actually rewritten counts
        # toward `updated`, so the response reflects the legacy rows that were
        # missed by the phone-only passes above.
        canon_scanned, canon_updated = self._canonicalize_rows()
        scanned += canon_scanned
        updated += canon_updated

        return {
            "scanned": scanned,
            "created": created,
            "updated": updated,
            "canonicalized": canon_updated,
        }

    def _canonicalize_rows(self) -> tuple[int, int]:
        """Bring every legacy customer row onto the canonical shape. Idempotent.

        A row is "legacy / needs canonicalization" iff it lacks a canonical
        `id`: canonical rows always carry a `cust-NNNN`, auth rows never do, so
        the absence of `id` is the reliable signal (the auth shape has neither
        `id` nor `name` nor `phone_normalized`, and names its timestamps
        `created_at`/`updated_at`). Such a row gets a `cust-NNNN` id, a `name`
        derived from its Google profile (full name, else "first last", else the
        email local-part), an `email_normalized`, a `phone_normalized` when it
        carries a phone, and `created`/`updated` copied from the auth
        `created_at`/`updated_at` when those canonical fields are absent. The
        originals (and `supertokens_user_id`) are preserved — the patch is
        purely additive. A row that already has an `id` is skipped, so a second
        run rewrites nothing.

        Returns ``(scanned, updated)``: rows examined and rows actually
        canonicalized.
        """
        coll = self.repository.collection
        scanned = 0
        updated = 0
        # Seed the id sequence from the current max so ids assigned in this loop
        # never collide regardless of `created` ordering.
        seq = self._max_customer_seq()
        for doc in list(coll.find({})):
            scanned += 1
            if doc.get("id"):
                continue  # already canonical — leave it untouched
            seq += 1
            patch: dict = {"id": f"cust-{seq}"}
            if not doc.get("name"):
                patch["name"] = _display_name(None, doc, doc.get("email"))
            if doc.get("email") and not doc.get("email_normalized"):
                patch["email_normalized"] = normalize_email(doc["email"])
            if doc.get("phone") and not doc.get("phone_normalized"):
                phone_norm = normalize_phone(doc["phone"])
                if phone_norm:
                    patch["phone_normalized"] = phone_norm
            if not doc.get("created"):
                patch["created"] = doc.get("created_at") or utcnow()
            if not doc.get("updated"):
                patch["updated"] = (
                    doc.get("updated_at") or doc.get("created_at") or utcnow()
                )
            coll.update_one({"_id": doc["_id"]}, {"$set": patch})
            updated += 1
        return scanned, updated

    def _max_customer_seq(self) -> int:
        """Highest numeric suffix among `cust-NNNN` ids (1000 when none)."""
        max_n = 1000
        for doc in self.repository.collection.find({"id": {"$regex": "^cust-"}}):
            try:
                n = int(str(doc["id"]).split("-")[-1])
                if n > max_n:
                    max_n = n
            except Exception:
                continue
        return max_n

    def _next_customer_id(self) -> str:
        # Derive the next id from the highest existing cust-NNNN suffix rather
        # than the most-recently-created row: when several rows share a `created`
        # timestamp to the microsecond, a created-ordered "latest" lookup is
        # non-deterministic and can hand out a duplicate id. The max suffix is
        # tie-proof, so ids never collide.
        return f"cust-{self._max_customer_seq() + 1}"

    # ----- auth linkage (SuperTokens) ----------------------------------

    def find_by_email(self, email: str) -> dict | None:
        return self.repository.find_by_email(email)

    def find_by_supertokens_id(self, supertokens_user_id: str) -> dict | None:
        return self.repository.find_by_supertokens_id(supertokens_user_id)

    def ensure_linked_to_supertokens(
        self, customer_doc: dict, supertokens_user_id: str
    ) -> None:
        if not customer_doc.get("supertokens_user_id"):
            self.repository.stamp_supertokens_id(customer_doc["_id"], supertokens_user_id)

    def get_or_create_for_auth(
        self,
        supertokens_user_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        profile: dict | None = None,
    ) -> dict:
        """Resolve the canonical customer for a SuperTokens sign-in.

        - Find by `supertokens_user_id` first, so repeat logins never duplicate.
        - Otherwise find an existing email match and link it (stamp the id,
          leaving its name untouched).
        - Otherwise create a fresh canonical customer row.

        The email-link branch IS the email-convergence step for an auth sign-in
        (cf. `resolve_identity`'s email rule): the SuperTokens id lands on the
        one record that already owns the email rather than minting a duplicate,
        which is exactly the outcome of a merge whose survivor is the auth
        record. The sparse-unique email index guarantees there is at most one
        such record to link.

        Always returns the matched/created Mongo document (with `_id`).
        """
        existing = self.repository.find_by_supertokens_id(supertokens_user_id)
        if existing is not None:
            return existing

        if email:
            norm = normalize_email(email)
            by_email = self.repository.find_by_email_normalized(
                norm
            ) or self.repository.find_by_email(email)
            if by_email is not None:
                if not by_email.get("supertokens_user_id"):
                    self.repository.stamp_supertokens_id(
                        by_email["_id"], supertokens_user_id
                    )
                return (
                    self.repository.find_by_supertokens_id(supertokens_user_id)
                    or by_email
                )

        merged_profile = dict(profile or {})
        if name and not merged_profile.get("full_name"):
            merged_profile["full_name"] = name
        self.create_from_profile(email or "", supertokens_user_id, merged_profile)
        return self.repository.find_by_supertokens_id(supertokens_user_id)

    def create_from_profile(
        self, email: str, supertokens_user_id: str, profile: dict
    ) -> str:
        now = utcnow()
        profile = profile or {}
        doc = {
            "id": self._next_customer_id(),
            "name": _display_name(None, profile, email),
            "email": email or None,
            "full_name": profile.get("full_name", ""),
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "supertokens_user_id": supertokens_user_id,
            "is_active": True,
            "notes": "",
            "created": now,
            "updated": now,
            "created_at": now,
            "updated_at": now,
        }
        # Only index a real address — an empty `email_normalized` would collide
        # under the sparse-unique email index.
        email_norm = normalize_email(email)
        if email_norm:
            doc["email_normalized"] = email_norm
        return self.repository.insert(doc)
