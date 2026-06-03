from .dns_records import DnsRecordsModule
from .whois_lookup import WhoisModule
from .subdomain_enum import SubdomainEnumModule
from .http_title import HttpTitleModule
from .reverse_dns import ReverseDnsModule
from .cert_transparency import CertTransparencyModule
from .ip_geolocation import IpGeolocationModule
from .leak_check import LeakCheckModule
from .github_search import GithubSearchModule
from .social_profiles import SocialProfilesModule
from .port_scan import PortScanModule

ALL_MODULES = [
    DnsRecordsModule,
    WhoisModule,
    SubdomainEnumModule,
    HttpTitleModule,
    ReverseDnsModule,
    CertTransparencyModule,
    IpGeolocationModule,
    LeakCheckModule,
    GithubSearchModule,
    SocialProfilesModule,
    PortScanModule,
]
