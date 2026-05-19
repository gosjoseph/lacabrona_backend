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

        - Existing customer: stamp `supertokens_user_id` (name fields untouched).
        - Existing employee: stamp `supertokens_user_id` (employee linking path).
        - Neither: create a new customer document using `profile`.

        Raises `UnknownUserError` only when `email` is empty.
        """
        if not email:
            raise UnknownUserError("Google signin did not return an email")

        customer = self.customer_service.find_by_email(email)
        if customer:
            self.customer_service.ensure_linked_to_supertokens(
                customer, supertokens_user_id
            )
            return {
                "user_type": "customer",
                "internal_id": str(customer["_id"]),
            }

        employee = self.employee_service.link_to_supertokens(
            email, supertokens_user_id
        )
        if employee:
            return {
                "user_type": "employee",
                "internal_id": str(employee["_id"]),
                "role": employee.get("role", "admin"),
            }

        internal_id = self.customer_service.create_from_profile(
            email, supertokens_user_id, profile or {}
        )
        return {"user_type": "customer", "internal_id": internal_id}
