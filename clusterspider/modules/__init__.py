from .dns_records import DnsRecordsModule
from .whois_lookup import WhoisModule
from .subdomain_enum import SubdomainEnumModule
from .http_title import HttpTitleModule
from .reverse_dns import ReverseDnsModule

ALL_MODULES = [
    DnsRecordsModule,
    WhoisModule,
    SubdomainEnumModule,
    HttpTitleModule,
    ReverseDnsModule,
]
