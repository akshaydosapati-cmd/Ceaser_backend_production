from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.models.desktop import DesktopDevice
from app.models.mixins import utc_now
from app.models.user import User
from app.services.browser_automation_service import BrowserAutomationService
from app.services.browser_automation_coordinator import BrowserAutomationCoordinator
from app.models.desktop import DesktopCommand
from datetime import timedelta

engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
Session=sessionmaker(bind=engine,autoflush=False,autocommit=False)

def seed(db,email="user@example.com",device="device-1",revoked=False):
    user=User(email=email);db.add(user);db.flush();item=DesktopDevice(user_id=user.id,device_id=device,device_name="Laptop",gateway_session_id="session",gateway_last_heartbeat_at=utc_now(),capabilities_json=["browser.navigate","browser.click","browser.upload"]);item.revoked_at=utc_now() if revoked else None;db.add(item);db.commit();return user,item

def test_browser_gateway_is_user_scoped_and_reuses_correlated_device_commands():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as db:
        first,_=seed(db,"first@example.com","first-device");second,_=seed(db,"second@example.com","second-device")
        result=BrowserAutomationService(db).dispatch(first,capability="browser.navigate",arguments={"url":"https://example.com"})
        assert result["status"]=="queued" and result["device_id"]=="first-device"
        assert result["device_id"]!="second-device"

def test_protected_write_requires_confirmation_before_gateway_submission():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as db:
        user,_=seed(db)
        blocked=BrowserAutomationService(db).dispatch(user,capability="browser.click",arguments={"action_type":"publish","external_write":True})
        assert blocked["error"]=="confirmation_required"
        assert BrowserAutomationService(db).dispatch(user,capability="browser.click",arguments={"action_type":"publish","external_write":True},confirmed=True)["status"]=="queued"

def test_revoked_or_disconnected_device_waits_and_unsafe_capability_is_rejected():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as db:
        user,_=seed(db,revoked=True);service=BrowserAutomationService(db)
        assert service.dispatch(user,capability="browser.navigate",arguments={"url":"https://example.com"})["error"]=="device_disconnected"
        assert service.dispatch(user,capability="browser.execute_javascript",arguments={})["error"]=="unsafe_action"

def test_model_driven_loop_queues_only_structured_safe_next_action(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as db:
        user,_=seed(db)
        command=DesktopCommand(user_id=user.id,device_id="device-1",request_id="inspect-1",task_id="task-1",agent_id="friday",capability="browser.inspect",request_json={"metadata":{"browser_goal":"Find the documentation","browser_step":1}},status="COMPLETED",result_json={"output":{"browser_session_id":"session-1","output":{"url":"https://example.com","title":"Example","text":"Documentation","buttons":[{"name":"Docs"}]}}},expires_at=utc_now()+timedelta(minutes=5),updated_at=utc_now());db.add(command);db.commit()
        monkeypatch.setattr("app.services.browser_automation_coordinator.generate_text_sync",lambda **_: '{"status":"continue","capability":"browser.click","arguments":{"target":{"role":"button","name":"Docs"}},"reason":"continue"}')
        queued=BrowserAutomationCoordinator(db).handle(command)
        assert queued.capability=="browser.click" and queued.request_json["arguments"]["browser_session_id"]=="session-1"

def test_model_proposed_external_write_stops_before_execution(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as db:
        user,_=seed(db)
        command=DesktopCommand(user_id=user.id,device_id="device-1",request_id="inspect-2",task_id="task-2",agent_id="friday",capability="browser.inspect",request_json={"metadata":{"browser_goal":"Publish a post","browser_step":2}},status="COMPLETED",result_json={"output":{"browser_session_id":"session-2","output":{"url":"https://example.com","text":"Share"}}},expires_at=utc_now()+timedelta(minutes=5),updated_at=utc_now());db.add(command);db.commit()
        monkeypatch.setattr("app.services.browser_automation_coordinator.generate_text_sync",lambda **_: '{"status":"continue","capability":"browser.click","arguments":{"target":{"role":"button","name":"Share"},"action_type":"publish","external_write":true},"reason":"publish"}')
        assert BrowserAutomationCoordinator(db).handle(command) is None
        assert db.query(DesktopCommand).count()==1
