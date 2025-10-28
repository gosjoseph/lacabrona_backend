from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

# Initialization code as requested
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://lacabronamvdit_db_user:dy2rXU5psJMa3G8v@lacabrona.yf4epef.mongodb.net/?appName=LaCabrona"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)


def get_db(db_name: str) -> Database:
    return client[db_name]


def get_collection(db_name: str, collection_name: str) -> Collection:
    return get_db(db_name)[collection_name]


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    _doc = dict(doc)
    if "_id" in _doc and isinstance(_doc["_id"], ObjectId):
        _doc["_id"] = str(_doc["_id"]) 
    return _doc


# Collections
def list_collections(db_name: str) -> List[str]:
    return get_db(db_name).list_collection_names()


def create_collection(db_name: str, collection_name: str) -> Dict[str, Any]:
    db = get_db(db_name)
    if collection_name not in db.list_collection_names():
        db.create_collection(collection_name)
    return {"collection": collection_name, "status": "ready"}


def drop_collection(db_name: str, collection_name: str) -> Dict[str, Any]:
    db = get_db(db_name)
    if collection_name in db.list_collection_names():
        db.drop_collection(collection_name)
        return {"collection": collection_name, "dropped": True}
    return {"collection": collection_name, "dropped": False}


# Documents
def insert_document(db_name: str, collection_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    col = get_collection(db_name, collection_name)
    res = col.insert_one(data)
    return {"inserted_id": str(res.inserted_id)}


def find_documents(
    db_name: str, collection_name: str, query: Optional[Dict[str, Any]] = None, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    col = get_collection(db_name, collection_name)
    cursor = col.find(query or {})
    if limit:
        cursor = cursor.limit(limit)
    return [serialize_doc(d) for d in cursor]


def get_document(db_name: str, collection_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
    col = get_collection(db_name, collection_name)
    try:
        oid = ObjectId(doc_id)
    except Exception:
        return None
    doc = col.find_one({"_id": oid})
    return serialize_doc(doc) if doc else None


def update_document(db_name: str, collection_name: str, doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    col = get_collection(db_name, collection_name)
    try:
        oid = ObjectId(doc_id)
    except Exception:
        return {"modified_count": 0}
    res = col.update_one({"_id": oid}, {"$set": updates})
    return {"modified_count": res.modified_count}


def delete_document(db_name: str, collection_name: str, doc_id: str) -> Dict[str, Any]:
    col = get_collection(db_name, collection_name)
    try:
        oid = ObjectId(doc_id)
    except Exception:
        return {"deleted_count": 0}
    res = col.delete_one({"_id": oid})
    return {"deleted_count": res.deleted_count}


# Fields (document-level)
def add_fields_to_document(db_name: str, collection_name: str, doc_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    return update_document(db_name, collection_name, doc_id, fields)


def remove_field_from_document(db_name: str, collection_name: str, doc_id: str, field: str) -> Dict[str, Any]:
    col = get_collection(db_name, collection_name)
    try:
        oid = ObjectId(doc_id)
    except Exception:
        return {"modified_count": 0}
    res = col.update_one({"_id": oid}, {"$unset": {field: ""}})
    return {"modified_count": res.modified_count}


# Fields (collection-level)
def add_fields_to_collection(db_name: str, collection_name: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    col = get_collection(db_name, collection_name)
    res = col.update_many({}, {"$set": fields})
    return {"matched_count": res.matched_count, "modified_count": res.modified_count}


def remove_field_from_collection(db_name: str, collection_name: str, field: str) -> Dict[str, Any]:
    col = get_collection(db_name, collection_name)
    res = col.update_many({}, {"$unset": {field: ""}})
    return {"matched_count": res.matched_count, "modified_count": res.modified_count}

