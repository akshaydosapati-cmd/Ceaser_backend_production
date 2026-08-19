from app.services.orchestrator.orchestrator import CeaserOrchestrator


def test_explicit_artifact_requests_enter_workflow() -> None:
    orchestrator = CeaserOrchestrator.__new__(CeaserOrchestrator)

    assert orchestrator._is_explicit_workflow_creation_request("Create a presentation about quantum computing")
    assert orchestrator._is_explicit_workflow_creation_request("Write a structured DOCX report about batteries")
    assert orchestrator._is_explicit_workflow_creation_request("Prepare study notes for operating systems")
    assert orchestrator._is_explicit_workflow_creation_request("Make an Excel workbook for expenses")


def test_questions_do_not_create_artifacts() -> None:
    orchestrator = CeaserOrchestrator.__new__(CeaserOrchestrator)

    assert not orchestrator._is_explicit_workflow_creation_request("What is a presentation?")
    assert not orchestrator._is_explicit_workflow_creation_request("Explain how to create a report")
    assert not orchestrator._is_explicit_workflow_creation_request("Tell me about business plans")
