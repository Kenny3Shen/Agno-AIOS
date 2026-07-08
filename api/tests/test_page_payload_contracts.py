from api.services import approvals_service, memory_service, page_payloads


def test_page_payloads_share_only_metric_and_record_item_types() -> None:
    assert hasattr(page_payloads, "PageMetric")
    assert hasattr(page_payloads, "PageRecord")
    assert not hasattr(page_payloads, "Page" + "Payload")


def test_page_services_export_page_specific_payload_responses() -> None:
    assert hasattr(approvals_service, "ApprovalListResponse")
    assert hasattr(memory_service, "MemoryPayloadResponse")
    assert not hasattr(approvals_service, "Approval" + "Payload")
    assert not hasattr(memory_service, "Memory" + "Payload")
