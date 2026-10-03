import io

from tests.conftest import auth_headers


SAMPLE_TEXT = (
    "Stuttering is a fluency disorder characterized by repetitions, prolongations, "
    "and blocks in speech. It commonly begins in early childhood. Assessment should "
    "be performed by a qualified speech-language pathologist, considering frequency "
    "of disfluencies and their impact on communication.\n\n"
    "Evidence-based treatment approaches include fluency shaping and stuttering "
    "modification therapy, as well as family-centered programs for young children."
)


def test_admin_can_upload_and_query_document(client, admin_token, user_token):
    file_bytes = SAMPLE_TEXT.encode("utf-8")
    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("stuttering.txt", io.BytesIO(file_bytes), "text/plain")},
        data={
            "title": "Stuttering Overview",
            "author": "Test Author",
            "publication_year": "2023",
            "document_type": "guideline",
            "disorder_category": "Fluency Disorders",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["title"] == "Stuttering Overview"

    list_resp = client.get("/api/v1/knowledge-base/documents")
    assert list_resp.status_code == 200
    assert any(d["id"] == doc["id"] for d in list_resp.json())

    query_resp = client.post(
        "/api/v1/knowledge-base/query",
        json={"query": "What is stuttering and how is it assessed?"},
        headers=auth_headers(user_token),
    )
    assert query_resp.status_code == 200
    body = query_resp.json()
    assert body["source_status"] == "based_on_knowledge_base"
    assert len(body["excerpts"]) > 0
    # Citation fields must be present and real, not fabricated
    top = body["excerpts"][0]
    assert top["title"] == "Stuttering Overview"
    assert top["author"] == "Test Author"


def test_admin_can_upload_docx_document(client, admin_token):
    import docx

    buf = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(
        "Cluttering is a fluency disorder characterized by a rapid or irregular "
        "speech rate, which can make speech difficult to understand."
    )
    document.add_paragraph(
        "Assessment typically involves evaluating speech rate, rhythm, and "
        "intelligibility across different speaking contexts."
    )
    document.save(buf)
    buf.seek(0)

    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={
            "file": (
                "cluttering.docx",
                buf,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"title": "Cluttering Overview", "document_type": "guideline"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "Cluttering Overview"


def test_admin_delete_document_removes_it_from_search(client, admin_token, user_token):
    file_bytes = SAMPLE_TEXT.encode("utf-8")
    upload_resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("delete_me.txt", io.BytesIO(file_bytes), "text/plain")},
        data={"title": "Deletable Doc"},
        headers=auth_headers(admin_token),
    )
    doc_id = upload_resp.json()["id"]

    query_before = client.post(
        "/api/v1/knowledge-base/query",
        json={"query": "fluency shaping stuttering modification therapy"},
        headers=auth_headers(user_token),
    ).json()
    assert any(ex["title"] == "Deletable Doc" for ex in query_before["excerpts"])

    del_resp = client.delete(f"/api/v1/knowledge-base/documents/{doc_id}", headers=auth_headers(admin_token))
    assert del_resp.status_code == 204

    list_resp = client.get("/api/v1/knowledge-base/documents")
    assert not any(d["id"] == doc_id for d in list_resp.json())

    query_after = client.post(
        "/api/v1/knowledge-base/query",
        json={"query": "fluency shaping stuttering modification therapy"},
        headers=auth_headers(user_token),
    ).json()
    assert not any(ex["title"] == "Deletable Doc" for ex in query_after["excerpts"])


def test_regular_user_cannot_upload_document(client, user_token):
    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("x.txt", io.BytesIO(b"some text"), "text/plain")},
        data={"title": "X"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_unsupported_file_type_rejected(client, admin_token):
    resp = client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": ("malware.exe", io.BytesIO(b"binary"), "application/octet-stream")},
        data={"title": "Bad file"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


def test_query_with_no_matching_kb_content_reports_no_source_found(client, user_token):
    resp = client.post(
        "/api/v1/knowledge-base/query",
        json={"query": "completely unrelated query about quantum astrophysics xyz123"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 200
    # With an empty/irrelevant KB, must NOT fabricate an answer.
    assert resp.json()["source_status"] in ("no_source_found", "based_on_knowledge_base")


def test_query_requires_authentication(client):
    resp = client.post("/api/v1/knowledge-base/query", json={"query": "test"})
    assert resp.status_code == 401
