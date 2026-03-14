from pydantic import BaseModel
from typing import Optional, List


class ICPContext(BaseModel):
    description: Optional[str] = None
    ideal_roles: Optional[List[str]] = None


class EnrichRequest(BaseModel):
    url: str
    icp: Optional[ICPContext] = None
    offer_context: Optional[str] = None
    depth: str = "standard"  # quick | standard | deep


class CompanyInfo(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    size_estimate: Optional[str] = None
    stage: Optional[str] = None
    business_model: Optional[str] = None
    founded_estimate: Optional[str] = None
    hq: Optional[str] = None


class TechStack(BaseModel):
    crm: Optional[str] = None
    hosting: Optional[str] = None
    analytics: Optional[str] = None
    payments: Optional[str] = None
    support: Optional[str] = None
    signals: Optional[List[str]] = None


class Signals(BaseModel):
    recent_funding: Optional[str] = None
    hiring: Optional[str] = None
    news: Optional[str] = None
    growth_signal: Optional[str] = None


class ICPFit(BaseModel):
    score: Optional[int] = None
    reasoning: Optional[str] = None


class Metadata(BaseModel):
    enriched_at: str
    depth: str
    confidence: str
    credits_used: int


class EnrichResponse(BaseModel):
    company: CompanyInfo
    tech_stack: Optional[TechStack] = None
    signals: Optional[Signals] = None
    icp_fit: Optional[ICPFit] = None
    pain_hypothesis: Optional[str] = None
    outreach_angle: Optional[str] = None
    opening_line: Optional[str] = None
    metadata: Metadata


class GenerateKeyRequest(BaseModel):
    name: Optional[str] = None


class GenerateKeyResponse(BaseModel):
    api_key: str
    name: str
    created_at: str


class UsageResponse(BaseModel):
    api_key_prefix: str
    calls_today: int
    rate_limit: int
    recent_calls: list
