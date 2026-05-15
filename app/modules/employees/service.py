from app.modules.employees.repository import EmployeeRepository


class EmployeeService:
    def __init__(self, repository: EmployeeRepository):
        self.repository = repository

    def link_to_supertokens(self, email: str, supertokens_user_id: str) -> dict | None:
        """Stamp the SuperTokens user id on an existing employee. Returns the doc or None."""
        existing = self.repository.find_by_email(email)
        if not existing:
            return None
        if not existing.get("supertokens_user_id"):
            self.repository.stamp_supertokens_id(existing["_id"], supertokens_user_id)
        return existing
