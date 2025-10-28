from fastapi import APIRouter, HTTPException

from .model import (
    CreateCollectionRequest,
    DocumentBody,
    FieldsBody,
    QueryBody,
    UpdateBody,
)
from . import service


router = APIRouter(prefix="/mongo", tags=["Mongo DB"])


# Collections
@router.get("/{db}/collections")
def list_collections(db: str):
    return {"collections": service.list_collections(db)}


@router.post("/{db}/collections")
def create_collection(db: str, body: CreateCollectionRequest):
    return service.create_collection(db, body.name)


@router.delete("/{db}/collections/{collection}")
def drop_collection(db: str, collection: str):
    return service.drop_collection(db, collection)


# Documents
@router.post("/{db}/{collection}/documents")
def insert_document(db: str, collection: str, body: DocumentBody):
    return service.insert_document(db, collection, body.data)


@router.post("/{db}/{collection}/search")
def find_documents(db: str, collection: str, body: QueryBody | None = None):
    q = body.filter if body else {}
    limit = body.limit if body else None
    return {"documents": service.find_documents(db, collection, q, limit)}


@router.get("/{db}/{collection}/documents/{doc_id}")
def get_document(db: str, collection: str, doc_id: str):
    doc = service.get_document(db, collection, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/{db}/{collection}/documents/{doc_id}")
def update_document(db: str, collection: str, doc_id: str, body: UpdateBody):
    return service.update_document(db, collection, doc_id, body.updates)


@router.delete("/{db}/{collection}/documents/{doc_id}")
def delete_document(db: str, collection: str, doc_id: str):
    return service.delete_document(db, collection, doc_id)


# Fields (document-level)
@router.patch("/{db}/{collection}/documents/{doc_id}/fields")
def add_fields_to_document(db: str, collection: str, doc_id: str, body: FieldsBody):
    return service.add_fields_to_document(db, collection, doc_id, body.fields)


@router.delete("/{db}/{collection}/documents/{doc_id}/fields/{field}")
def remove_field_from_document(db: str, collection: str, doc_id: str, field: str):
    return service.remove_field_from_document(db, collection, doc_id, field)


# Fields (collection-level)
@router.patch("/{db}/{collection}/fields")
def add_fields_to_collection(db: str, collection: str, body: FieldsBody):
    return service.add_fields_to_collection(db, collection, body.fields)


@router.delete("/{db}/{collection}/fields/{field}")
def remove_field_from_collection(db: str, collection: str, field: str):
    return service.remove_field_from_collection(db, collection, field)
