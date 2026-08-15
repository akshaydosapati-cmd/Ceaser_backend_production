from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.intelligence.ai.model_router.request_builder import request_for_agent
from app.intelligence.ai.sync import generate_text_sync
from app.models.desktop import DesktopCommand
from app.models.social_publish import SocialPublishTask
from app.models.mixins import utc_now
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.browser_automation_service import BrowserAutomationService


class SocialMediaReference(BaseModel):
    file_reference: str
    filename: str
    mime_type: str
    size: int = Field(ge=1, le=104857600)
    device_id: str
    source: Literal["chat_attachment", "file_picker", "attachment", "selected_file", "explicit_path", "recent_context"]
    fingerprint: str


class SocialPostDraft(BaseModel):
    platform: str
    media: list[SocialMediaReference] = Field(min_length=1, max_length=10)
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    mentions: list[str] = Field(default_factory=list, max_length=20)
    location: str | None = None
    alt_text: str | None = None
    collaborators: list[str] = Field(default_factory=list, max_length=10)
    audience: str | None = None
    comments_enabled: bool | None = None
    like_count_visibility: str | None = None
    cross_post_targets: list[str] = Field(default_factory=list, max_length=5)
    generated_by: str
    status: Literal["draft", "waiting_for_confirmation", "published", "partial", "failed"] = "draft"


class SocialPublishingService:
    def __init__(self, db: Session): self.db=db; self.browser=BrowserAutomationService(db)

    def prepare(self,user:User,*,prompt:str,platform:str,media:dict|None,device_id:str|None=None,task_id:str|None=None):
        if not media:return {"status":"clarification_required","message":"Which image or video would you like me to post?"}
        try:reference=SocialMediaReference.model_validate(media)
        except Exception:return {"status":"failed","error":"invalid_file_context"}
        if reference.device_id!=device_id:return {"status":"failed","error":"device_mismatch"}
        task_id=task_id or f"social_{uuid4().hex}";self._event(user.id,"social.file_resolved",task_id,{"filename":reference.filename,"source":reference.source})
        self._event(user.id,"social.draft_started",task_id,{"platform":platform})
        explicit=self._explicit_content(prompt);creative=self._nova(prompt,platform,reference.filename) if not explicit["caption"] or self._asks_generation(prompt) else {}
        draft=SocialPostDraft(platform=platform.lower(),media=[reference],caption=explicit["caption"] or str(creative.get("caption") or ""),hashtags=explicit["hashtags"] or list(creative.get("hashtags") or [])[:30],alt_text=str(creative.get("alt_text") or "") or None,generated_by="user" if explicit["caption"] else "nova",status="waiting_for_confirmation")
        if creative:self._event(user.id,"social.caption_generated",task_id,{"platform":platform})
        pending=SocialPublishTask(user_id=user.id,task_id=task_id,device_id=device_id,platform=platform.lower(),status="WAITING_FOR_CONFIRMATION",draft_encrypted="",expires_at=utc_now()+timedelta(minutes=15));pending.draft=draft.model_dump(mode="json");self.db.add(pending);self.db.commit()
        self._event(user.id,"social.draft_ready",task_id,{"platform":platform});self._event(user.id,"social.preview_ready",task_id,{"platform":platform,"filename":reference.filename});self._event(user.id,"social.waiting_for_confirmation",task_id,{"platform":platform})
        return {"status":"waiting_for_confirmation","task_id":task_id,"draft":draft.model_dump(mode="json"),"preview":self.preview(draft)}

    def stage_publish_action(self,user:User,*,task_id:str,browser_session_id:str,target:dict,verification:dict):
        pending=self.db.query(SocialPublishTask).filter(SocialPublishTask.user_id==user.id,SocialPublishTask.task_id==task_id).first()
        if not pending or pending.status not in {"WAITING_FOR_CONFIRMATION","DRAFT"}:return {"status":"failed","error":"pending_publish_not_found"}
        if not browser_session_id or not isinstance(target,dict) or not target:return {"status":"failed","error":"invalid_publish_action"}
        draft=pending.draft;draft["pending_action"]={"browser_session_id":browser_session_id,"target":target,"verification":verification or {}}
        pending.draft=draft;pending.browser_session_id=browser_session_id;self.db.commit()
        clean={k:v for k,v in draft.items() if k!="pending_action"}
        return {"status":"waiting_for_confirmation","task_id":task_id,"preview":self.preview(SocialPostDraft.model_validate(clean))}

    def confirm(self,user:User,*,task_id:str,device_id:str,browser_session_id:str|None=None,target:dict|None=None,verification:dict|None=None):
        pending=self.db.query(SocialPublishTask).filter(SocialPublishTask.user_id==user.id,SocialPublishTask.task_id==task_id).first()
        if not pending:return {"status":"failed","error":"pending_publish_not_found"}
        expires=pending.expires_at
        if expires.tzinfo is None:expires=expires.replace(tzinfo=utc_now().tzinfo)
        if expires<utc_now():pending.status="EXPIRED";self.db.commit();return {"status":"failed","error":"confirmation_expired"}
        if pending.device_id!=device_id:return {"status":"failed","error":"device_mismatch"}
        if pending.status=="PUBLISHED":return {"status":"completed","verified":True,"duplicate_prevented":True,"request_id":pending.published_request_id}
        action=(pending.draft or {}).get("pending_action") or {}
        if not action:return {"status":"failed","error":"publish_action_not_ready"}
        browser_session_id=str(action.get("browser_session_id") or "");target=action.get("target") or {};verification=action.get("verification") or {}
        if not browser_session_id or not target:return {"status":"failed","error":"publish_action_not_ready"}
        existing=self.db.query(DesktopCommand).filter(DesktopCommand.user_id==user.id,DesktopCommand.task_id==task_id,DesktopCommand.capability=="browser.click").order_by(DesktopCommand.created_at.desc()).first()
        if existing and existing.status=="COMPLETED" and ((existing.result_json or {}).get("verification") or {}).get("verified"):
            return {"status":"completed","verified":True,"duplicate_prevented":True,"request_id":existing.request_id}
        result=self.browser.dispatch(user,capability="browser.click",arguments={"browser_session_id":browser_session_id,"target":target,"action_type":"publish","external_write":True,"verification":verification},task_id=task_id,device_id=device_id,confirmed=True)
        if result.get("status")=="queued":self._event(user.id,"social.publish_started",task_id,{})
        if result.get("status")=="queued":pending.status="PUBLISHING";pending.browser_session_id=browser_session_id;pending.published_request_id=result.get("request_id");self.db.commit()
        return result

    def edit_caption(self,user:User,*,task_id:str,caption:str):
        pending=self.db.query(SocialPublishTask).filter(SocialPublishTask.user_id==user.id,SocialPublishTask.task_id==task_id).first()
        if not pending or pending.status not in {"WAITING_FOR_CONFIRMATION","DRAFT"}:return {"status":"failed","error":"pending_publish_not_found"}
        draft=pending.draft;draft["caption"]=str(caption)[:2200];draft["generated_by"]="user";draft["status"]="waiting_for_confirmation";pending.draft=draft;pending.status="WAITING_FOR_CONFIRMATION";self.db.commit();return {"status":"waiting_for_confirmation","draft":draft,"preview":self.preview(SocialPostDraft.model_validate(draft))}

    def complete(self,command:DesktopCommand):
        if command.capability!="browser.click":return
        pending=self.db.query(SocialPublishTask).filter(SocialPublishTask.user_id==command.user_id,SocialPublishTask.task_id==command.task_id).first()
        if not pending:return
        verified=command.status=="COMPLETED" and ((command.result_json or {}).get("verification") or {}).get("verified")
        pending.status="PUBLISHED" if verified else "FAILED";self.db.commit();self._event(command.user_id,"social.publish_verified" if verified else "social.publish_failed",command.task_id,{"platform":pending.platform})

    @staticmethod
    def _explicit_content(prompt):
        match=re.search(r"(?:use exactly|caption(?: is|:)?|with caption)\s*['\"]([^'\"]+)['\"]",prompt,re.I);hashtags=re.findall(r"(?<!\w)#[A-Za-z0-9_]+",prompt)
        return {"caption":match.group(1).strip() if match else "","hashtags":hashtags}
    @staticmethod
    def _asks_generation(prompt):return bool(re.search(r"\b(?:good|professional|creative|generate|write|make).{0,30}\b(?:caption|hashtags?)\b",prompt,re.I))
    @staticmethod
    def _nova(prompt,platform,filename):
        raw=generate_text_sync(instructions="You are Nova. Return JSON only with caption, hashtags, alt_text. Never invent people, locations, collaborators, cross-post targets, privacy changes, or account settings.",input_text=json.dumps({"request":prompt,"platform":platform,"filename":filename},ensure_ascii=True),max_output_tokens=800,model_request=request_for_agent("nova",context_size_estimate=max(1,len(prompt)//4)))
        text=re.sub(r"^```(?:json)?\s*|\s*```$","",str(raw).strip(),flags=re.I);return json.loads(text[text.find("{"):text.rfind("}")+1])
    @staticmethod
    def preview(draft):return {"platform":draft.platform,"media":[m.filename for m in draft.media],"caption":draft.caption,"hashtags":draft.hashtags,"mentions":draft.mentions or None,"location":draft.location,"collaborators":draft.collaborators or None,"comments":draft.comments_enabled,"cross_post":draft.cross_post_targets or None,"status":"waiting_for_confirmation"}
    def _event(self,user_id,action,task_id,metadata):AuditService(self.db).record(user_id=user_id,action=action,resource_type="social_post",resource_id=task_id,metadata={"task_id":task_id,**metadata})
