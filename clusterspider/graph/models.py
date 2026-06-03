from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class EntityType(str, Enum):
    DOMAIN = "Domain"
    IP = "IP"
    EMAIL = "Email"
    USERNAME = "Username"
    CERTIFICATE = "Certificate"
    ORGANIZATION = "Organization"
    LEAK_RECORD = "LeakRecord"
    PORT = "Port"


class RelationType(str, Enum):
    RESOLVES_TO = "RESOLVES_TO"
    HAS_SUBDOMAIN = "HAS_SUBDOMAIN"
    REGISTERED_BY = "REGISTERED_BY"
    BELONGS_TO_ORG = "BELONGS_TO_ORG"
    ISSUED_TO = "ISSUED_TO"
    APPEARS_IN = "APPEARS_IN"
    HAS_USERNAME = "HAS_USERNAME"
    BELONGS_TO_ASN = "BELONGS_TO_ASN"
    REVERSE_DNS = "REVERSE_DNS"
    NAMESERVER = "NAMESERVER"
    MAIL_EXCHANGE = "MAIL_EXCHANGE"
    FOUND_IN_REPO = "FOUND_IN_REPO"
    HAS_PORT = "HAS_PORT"


class NodeBase(BaseModel):
    user_id: str
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class DomainNode(NodeBase):
    value: str
    registrar: str | None = None
    created_date: str | None = None
    expiration_date: str | None = None


class IPNode(NodeBase):
    value: str
    version: str = "v4"
    geo_country: str | None = None
    geo_city: str | None = None
    geo_lat: float | None = None
    geo_lon: float | None = None


class EmailNode(NodeBase):
    value: str


class UsernameNode(NodeBase):
    value: str
    platform: str
    profile_url: str | None = None


class CertificateNode(NodeBase):
    fingerprint: str
    serial: str | None = None
    issuer: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    san_count: int | None = None


class OrganizationNode(NodeBase):
    name: str
    asn: str | None = None
    description: str | None = None


class LeakRecordNode(NodeBase):
    breach_name: str
    breach_date: str | None = None
    data_classes: list[str] = Field(default_factory=list)
    pwn_count: int | None = None


class PortNode(NodeBase):
    value: str  # "ip:port"
    port: int
    protocol: str = "tcp"
    service: str | None = None
    banner: str | None = None


class GraphEdge(BaseModel):
    from_label: EntityType
    from_key: dict[str, str]
    to_label: EntityType
    to_key: dict[str, str]
    rel_type: RelationType
    properties: dict = Field(default_factory=dict)
