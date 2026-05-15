from pymongo.database import Database

from app.core.utils import utcnow


class EmployeeRepository:
    def __init__(self, db: Database):
        self.collection = db.employees

    def find_by_email(self, email: str) -> dict | None:
        return self.collection.find_one({"email": email})

    def stamp_supertokens_id(self, mongo_id, supertokens_user_id: str) -> None:
        self.collection.update_one(
            {"_id": mongo_id},
            {"$set": {
                "supertokens_user_id": supertokens_user_id,
                "updated_at": utcnow(),
            }},
        )
