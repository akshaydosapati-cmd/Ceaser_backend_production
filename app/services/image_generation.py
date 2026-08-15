from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

class ImageGenerationRequest(BaseModel):
    prompt:str=Field(min_length=1,max_length=4000)
    aspect_ratio:str="1:1"
    size:str="1024x1024"
    count:int=Field(default=1,ge=1,le=4)
    style_hint:str|None=None
    output_format:Literal["png","jpeg","webp"]="png"

class ImageGenerationResult(BaseModel):
    asset_id:str|None=None
    reference:str|None=None
    mime_type:str|None=None
    width:int|None=None
    height:int|None=None
    provider:str|None=None
    status:Literal["completed","failed","image_generation_unavailable"]
    error_code:str|None=None

class ImageGenerationProvider(ABC):
    @abstractmethod
    def available(self)->bool:...
    @abstractmethod
    def generate(self,user_id:str,request:ImageGenerationRequest)->list[ImageGenerationResult]:...

class ImageGenerationService:
    def __init__(self,provider:ImageGenerationProvider|None=None):self.provider=provider
    def generate(self,user_id:str,request:ImageGenerationRequest):
        if not self.provider or not self.provider.available():return [ImageGenerationResult(status="image_generation_unavailable",error_code="image_generation_unavailable")]
        return self.provider.generate(user_id,request)
