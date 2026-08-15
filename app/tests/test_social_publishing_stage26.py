from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database.base import Base
from app.models.user import User
from app.services.social_publishing_service import SocialPublishingService
from app.models.social_publish import SocialPublishTask
from app.models.desktop import DesktopCommand
from app.models.mixins import utc_now
from datetime import timedelta

engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Session=sessionmaker(bind=engine)
def media(device="d1"):return{"file_reference":"f1","filename":"launch.mp4","mime_type":"video/mp4","size":100,"device_id":device,"source":"attachment","fingerprint":"abc"}
def test_no_file_clarifies_and_cross_device_is_rejected():
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with Session() as db:
  user=User(email="u@example.com");db.add(user);db.commit();service=SocialPublishingService(db)
  assert service.prepare(user,prompt="Post a picture",platform="instagram",media=None,device_id="d1")["status"]=="clarification_required"
  assert service.prepare(user,prompt="Post this",platform="instagram",media=media("other"),device_id="d1")["error"]=="device_mismatch"
def test_explicit_caption_wins_and_defaults_are_not_invented():
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with Session() as db:
  user=User(email="u2@example.com");db.add(user);db.commit();result=SocialPublishingService(db).prepare(user,prompt='Post this with caption "Launching CEASER today." #CEASER #VoiceAI',platform="instagram",media=media(),device_id="d1");draft=result["draft"]
  assert draft["caption"]=="Launching CEASER today." and draft["hashtags"]==["#CEASER","#VoiceAI"]
  assert draft["location"] is None and draft["collaborators"]==[] and draft["cross_post_targets"]==[] and result["status"]=="waiting_for_confirmation"
def test_nova_generates_bounded_content_without_overwriting_options(monkeypatch):
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with Session() as db:
  user=User(email="u3@example.com");db.add(user);db.commit();monkeypatch.setattr("app.services.social_publishing_service.generate_text_sync",lambda **_: '{"caption":"Professional launch","hashtags":["#CEASER"],"alt_text":"Launch video"}')
  draft=SocialPublishingService(db).prepare(user,prompt="Post this with a professional caption and hashtags",platform="instagram",media=media(),device_id="d1")["draft"]
  assert draft["generated_by"]=="nova" and draft["caption"]=="Professional launch" and draft["mentions"]==[] and draft["location"] is None
def test_confirmation_resumes_exact_encrypted_pending_draft_and_edit_stays_pending(monkeypatch):
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with Session() as db:
  user=User(email="u4@example.com");db.add(user);db.commit();service=SocialPublishingService(db);prepared=service.prepare(user,prompt='Post this with caption "Original"',platform="instagram",media=media(),device_id="d1",task_id="social-1")
  pending=db.query(SocialPublishTask).filter_by(task_id="social-1").one();assert "Original" not in pending.draft_encrypted
  edited=service.edit_caption(user,task_id="social-1",caption="Updated");assert edited["draft"]["caption"]=="Updated" and pending.status=="WAITING_FOR_CONFIRMATION"
  staged=service.stage_publish_action(user,task_id="social-1",browser_session_id="s1",target={"role":"button","name":"Share"},verification={"text_contains":"shared"});assert staged["status"]=="waiting_for_confirmation"
  monkeypatch.setattr(service.browser,"dispatch",lambda *a,**k:{"status":"queued","request_id":"publish-1"})
  result=service.confirm(user,task_id="social-1",browser_session_id="evil",target={"role":"button","name":"Delete"},verification={},device_id="d1")
  assert result["status"]=="queued" and pending.status=="PUBLISHING" and pending.published_request_id=="publish-1"
def test_verified_completion_enables_duplicate_protection(monkeypatch):
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with Session() as db:
  user=User(email="u5@example.com");db.add(user);db.commit();service=SocialPublishingService(db);service.prepare(user,prompt='Post this with caption "Ready"',platform="instagram",media=media(),device_id="d1",task_id="social-2")
  pending=db.query(SocialPublishTask).filter_by(task_id="social-2").one();pending.status="PUBLISHING";pending.published_request_id="publish-2"
  command=DesktopCommand(user_id=user.id,device_id="d1",request_id="publish-2",task_id="social-2",agent_id="friday",capability="browser.click",request_json={},status="COMPLETED",result_json={"verification":{"verified":True}},expires_at=utc_now()+timedelta(minutes=1),updated_at=utc_now());db.add(command);db.commit();service.complete(command)
  duplicate=service.confirm(user,task_id="social-2",device_id="d1");assert duplicate["duplicate_prevented"] is True and pending.status=="PUBLISHED"
