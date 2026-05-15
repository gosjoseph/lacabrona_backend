from app.core.utils import utcnow
from app.modules.customers.repository import CustomerRepository


class CustomerService:
    def __init__(self, repository: CustomerRepository):
        self.repository = repository

    def find_by_email(self, email: str) -> dict | None:
        return self.repository.find_by_email(email)

    def ensure_linked_to_supertokens(
        self, customer_doc: dict, supertokens_user_id: str
    ) -> None:
        if not customer_doc.get("supertokens_user_id"):
            self.repository.stamp_supertokens_id(customer_doc["_id"], supertokens_user_id)

    def create_from_profile(
        self, email: str, supertokens_user_id: str, profile: dict
    ) -> str:
        now = utcnow()
        new_doc = {
            "email": email,
            "full_name": profile.get("full_name", ""),
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "supertokens_user_id": supertokens_user_id,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        return self.repository.insert(new_doc)
