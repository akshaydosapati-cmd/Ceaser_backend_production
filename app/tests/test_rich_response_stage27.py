import pytest
from pydantic import ValidationError

from app.schemas.rich_response import ResponseAsset, ResponseBlock
from app.services.image_generation import ImageGenerationRequest, ImageGenerationService
from app.services.rich_response_service import AssetReferenceService, RichResponseService
from app.core.database.base import Base
from app.models.file import File
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

def test_normal_chat_stays_simple_and_has_no_reasoning():
    rich=RichResponseService.compose({"response":"Quantum computing uses qubits.","selected_agents":[]},user_id="u1",task_id="t1")
    assert rich.primary_text=="Quantum computing uses qubits." and [b.type for b in rich.blocks]==["markdown"]
    assert "reasoning" not in rich.model_dump_json().lower() and "prompt" not in rich.model_dump_json().lower()

def test_research_uses_only_real_sources_and_images():
    payload={"response":"Research complete.","selected_agents":["Alex"],"research":{"sources":[{"title":"Report","url":"https://example.com/report","publisher":"Example","snippet":"Evidence"},{"title":"Fake","url":"invented"}],"images":[{"title":"Chart","url":"https://example.com/report","image_url":"https://example.com/chart.jpg","source":"Example"},{"title":"Bad","url":"","image_url":"made-up"}]}}
    rich=RichResponseService.compose(payload,user_id="u1",task_id="t1")
    assert len(rich.sources)==1 and len([b for b in rich.blocks if b.type=="image"])==1

def test_table_chart_and_web_image_contracts():
    assert ResponseBlock(type="table",columns=["Name","Value"],rows=[["A",1]]).rows[0][1]==1
    assert ResponseBlock(type="chart",chart_type="bar",labels=["A"],series=[{"name":"Count","data":[1]}]).chart_type=="bar"
    with pytest.raises(ValidationError):ResponseBlock(type="image",url="https://example.com/a.jpg")

def test_project_actions_are_capability_controlled():
    rich=RichResponseService.compose({"response":"Done","selected_agents":["Bolt"],"project_result":{"project_id":"p1","name":"App","status":"completed","build_status":"passed","test_status":"passed","actions":[{"label":"Open","capability":"project.open_vscode"},{"label":"Shell","capability":"shell.raw"}]}},user_id="u1")
    project=next(b for b in rich.blocks if b.type=="project")
    assert [a.capability for a in project.actions]==["project.open_vscode"]

def test_image_generation_unavailable_is_truthful():
    result=ImageGenerationService().generate("u1",ImageGenerationRequest(prompt="Create a poster"))[0]
    assert result.status=="image_generation_unavailable" and result.asset_id is None

def test_assets_are_user_scoped_and_hide_user_id():
    asset=ResponseAsset(asset_id="asset1",user_id="u1",filename="result.png",mime_type="image/png",size=10,reference="storage://asset1",origin="generated")
    assert "user_id" not in asset.model_dump() and asset.user_id=="u1"

def test_social_confirmation_status_is_representable():
    rich=RichResponseService.compose({"response":"Review it.","selected_agents":["Nova"],"metadata":{"social_publish":{"status":"waiting_for_confirmation","preview":{"platform":"instagram","media":["a.jpg"]}}}},user_id="u1")
    assert rich.status=="waiting_for_confirmation" and any(b.type=="status" for b in rich.blocks)

def test_existing_activity_names_normalize_without_internal_reasoning():
    events=[RichResponseService.normalize_activity(name,task_id="t1",metadata={"platform":"instagram","secret":"hidden"}) for name in ("bolt.build_passed","browser.navigation_started","social.waiting_for_confirmation")]
    assert [event.agent for event in events]==["Bolt","Friday","Nova"]
    assert all("secret" not in event.safe_metadata for event in events)

def test_asset_continuation_is_stable_and_cross_user_safe():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    with Session() as db:
        asset=File(user_id="user-a",name="poster.png",file_type="image/png",storage_path="users/user-a/poster.png");db.add(asset);db.commit()
        service=AssetReferenceService(db)
        assert service.resolve(user_id="user-a",asset_id=asset.id).name=="poster.png"
        assert service.resolve(user_id="user-b",asset_id=asset.id) is None
