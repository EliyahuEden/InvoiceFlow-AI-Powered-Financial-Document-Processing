import pytest

from app.core.config import get_settings


@pytest.mark.parametrize("route", ["/api/invoices/upload", "/api/knowledge/documents"])
@pytest.mark.parametrize("size_header", [True, False])
def test_multipart_limit_runs_before_parsing(client, monkeypatch, route, size_header):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024)
    body = b"--invoiceflow\r\nContent-Disposition: form-data; name=\"file\"; filename=\"example.pdf\"\r\n\r\n"
    body += b"x" * (80 * 1024) + b"\r\n--invoiceflow--\r\n"
    headers = {"Content-Type": "multipart/form-data; boundary=invoiceflow"}
    data = body if size_header else iter((body[:4096], body[4096:]))
    response = client.post(route, content=data, headers=headers)
    assert response.status_code == 413
