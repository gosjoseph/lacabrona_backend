"""Auth orchestration: maps a SuperTokens Google signin to a customer or employee.

Kept independent of the SuperTokens SDK so it can be unit-tested without
spinning up the core or constructing SDK response objects.
"""

from typing import Optional

from pymongo.database import Database

from app.modules.auth.exceptions import UnknownUserError
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.service import CustomerService
from app.modules.employees.repository import EmployeeRepository
from app.modules.employees.service import EmployeeService


class AuthService:
    def __init__(
        self,
        customer_service: CustomerService,
        employee_service: EmployeeService,
    ):
        self.customer_service = customer_service
        self.employee_service = employee_service

    @classmethod
    def from_db(cls, db: Database) -> "AuthService":
        return cls(
            customer_service=CustomerService(CustomerRepository(db)),
            employee_service=EmployeeService(EmployeeRepository(db)),
        )

    def resolve_session_user(self, supertokens_user_id: str) -> Optional[dict]:
        """Read-only lookup of the record linked to a SuperTokens user id.

        Returns `{"user_type": "customer"|"employee", "doc": <mongo doc>}` or
        `None` when no record is linked. Unlike `resolve_user_type`, this never
        creates or mutates a document — it backs the `/auth/me` rehydration
        endpoint, where the user already exists from a prior signin.
        """
        customer = self.customer_service.find_by_supertokens_id(supertokens_user_id)
        if customer:
            return {"user_type": "customer", "doc": customer}

        employee = self.employee_service.find_by_supertokens_id(supertokens_user_id)
        if employee:
            return {"user_type": "employee", "doc": employee}

        return None

    def resolve_user_type(
        self,
        email: str,
        supertokens_user_id: str,
        profile: Optional[dict] = None,
    ) -> dict:
        """Link the Google signin to an existing record or create a new customer.

        La Cabrona resolves CUSTOMER-FIRST by email: an existing or already
        linked customer always wins over an employee. Only when there is no
        customer at all does an employee email match.

        - Existing/linked customer: linked via `get_or_create_for_auth` (finds
          by SuperTokens id, else by email; name fields untouched).
        - Otherwise an employee email: stamp `supertokens_user_id`.
        - Otherwise: create a fresh canonical customer from `profile`.

        Raises `UnknownUserError` only when `email` is empty.
        """
        if not email:
            raise UnknownUserError("Google signin did not return an email")

        # Customer-first: an existing customer (linked or email-matched) wins.
        has_customer = (
            self.customer_service.find_by_supertokens_id(supertokens_user_id)
            is not None
            or self.customer_service.find_by_email(email) is not None
        )
        if not has_customer:
            employee = self.employee_service.link_to_supertokens(
                email, supertokens_user_id
            )
            if employee:
                return {
                    "user_type": "employee",
                    "internal_id": str(employee["_id"]),
                    "role": employee.get("role", "admin"),
                }

        customer = self.customer_service.get_or_create_for_auth(
            supertokens_user_id, email, profile=profile
        )
        return {"user_type": "customer", "internal_id": str(customer["_id"])}
