#!/usr/bin/env python3
"""Bootstrap a Cloudflare zone from Linux without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"

DEFAULT_ZONE_SETTINGS = {
    "always_use_https": "on",
    "automatic_https_rewrites": "on",
    "brotli": "on",
    "email_obfuscation": "on",
    "http3": "on",
    "ipv6": "on",
    "security_level": "medium",
    "ssl": "full",
    "tls_1_3": "zrt",
}

SENSITIVE_PATHS_RULE = {
    "ref": "protect_sensitive_paths",
    "description": "Protect Sensitive Paths",
    "action": "block",
    "expression": (
        '('
        'ends_with(http.request.uri.path, "/wp-config.php") or '
        'ends_with(http.request.uri.path, "/.htaccess") or '
        'ends_with(http.request.uri.path, "/xmlrpc.php") or '
        'ends_with(http.request.uri.path, "/php.ini") or '
        'starts_with(http.request.uri.path, "/cgi-bin") or '
        'starts_with(http.request.uri.path, "/cgi-bin/")'
        ')'
    ),
    "enabled": True,
}


class CloudflareError(RuntimeError):
    """Raised when the Cloudflare API returns an error."""


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def detect_public_ip(url: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read().decode("utf-8").strip() or None
    except OSError:
        return None


@dataclass
class CloudflareClient:
    api_token: Optional[str] = None
    auth_email: Optional[str] = None
    global_api_key: Optional[str] = None
    dry_run: bool = False
    verbose: bool = False

    def __post_init__(self) -> None:
        if not self.api_token and not (self.auth_email and self.global_api_key):
            raise ValueError(
                "Provide either --api-token or both --auth-email and --global-api-key."
            )

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ansible-stack-cloudflare-bootstrap/1.0",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        else:
            headers["X-Auth-Email"] = self.auth_email or ""
            headers["X-Auth-Key"] = self.global_api_key or ""
        return headers

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Any:
        path = "/" + path.lstrip("/")
        url = CLOUDFLARE_API_BASE + path
        if query:
            query_string = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}
            )
            if query_string:
                url = f"{url}?{query_string}"

        if self.dry_run and method in {"POST", "PUT", "PATCH", "DELETE"}:
            print(f"DRY-RUN {method} {url}")
            if payload is not None:
                print(json.dumps(payload, indent=2, sort_keys=True))
            return {}

        if self.verbose:
            eprint(f"{method} {url}")

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url=url,
            data=body,
            method=method,
            headers=self._headers(),
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise CloudflareError(f"{method} {path} failed: HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise CloudflareError(f"{method} {path} failed: {exc.reason}") from exc

        if not raw:
            return {}

        data = json.loads(raw)
        if not data.get("success", False):
            raise CloudflareError(
                f"{method} {path} failed: {json.dumps(data.get('errors', []), ensure_ascii=True)}"
            )
        return data.get("result")

    def paginate(self, path: str, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        page = 1
        per_page = 100

        while True:
            merged_query = dict(query or {})
            merged_query.update({"page": page, "per_page": per_page})
            page_result = self.request("GET", path, query=merged_query)
            if not isinstance(page_result, list):
                return result
            result.extend(page_result)
            if len(page_result) < per_page:
                return result
            page += 1


def get_zone(client: CloudflareClient, domain: str) -> Dict[str, Any]:
    zones = client.paginate("zones", {"name": domain})
    for zone in zones:
        if zone.get("name") == domain:
            return zone
    raise CloudflareError(f"Zone '{domain}' was not found.")


def ensure_zone_settings(client: CloudflareClient, zone_id: str, settings: Dict[str, Any]) -> None:
    for setting_name, setting_value in settings.items():
        try:
            client.request(
                "PATCH",
                f"zones/{zone_id}/settings/{setting_name}",
                {"value": setting_value},
            )
            print(f"Ensured zone setting {setting_name}={setting_value}")
        except CloudflareError as exc:
            eprint(f"WARNING: could not update zone setting {setting_name}: {exc}")


def ensure_dnssec(client: CloudflareClient, zone_id: str) -> None:
    try:
        dnssec = client.request("GET", f"zones/{zone_id}/dnssec")
        if dnssec.get("status") != "active":
            client.request("PATCH", f"zones/{zone_id}/dnssec", {"status": "active"})
            print("Enabled DNSSEC")
        else:
            print("DNSSEC already active")
    except CloudflareError as exc:
        eprint(f"WARNING: could not enable DNSSEC: {exc}")


def list_dns_records(client: CloudflareClient, zone_id: str) -> List[Dict[str, Any]]:
    return client.paginate(f"zones/{zone_id}/dns_records")


def record_matches(existing: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    keys = ("type", "name", "content", "proxied", "ttl")
    for key in keys:
        if key in expected and existing.get(key) != expected.get(key):
            return False
    return True


def ensure_dns_record(
    client: CloudflareClient,
    zone_id: str,
    existing_records: List[Dict[str, Any]],
    expected: Dict[str, Any],
) -> None:
    name = expected["name"]
    record_type = expected["type"]
    same_name = [item for item in existing_records if item.get("name") == name]

    if record_type in {"A", "AAAA"}:
        conflicting = [item for item in same_name if item.get("type") == "CNAME"]
        if conflicting:
            raise CloudflareError(
                f"Cannot create {record_type} record for '{name}' because a CNAME already exists."
            )
    if record_type == "CNAME":
        conflicting = [item for item in same_name if item.get("type") in {"A", "AAAA"}]
        if conflicting:
            print(f"Skipping CNAME for {name}; A/AAAA records already exist.")
            return

    same_type = [item for item in same_name if item.get("type") == record_type]
    for current in same_type:
        if record_matches(current, expected):
            print(f"DNS record already present: {record_type} {name} -> {expected['content']}")
            return

    if same_type:
        record_id = same_type[0]["id"]
        client.request(
            "PUT",
            f"zones/{zone_id}/dns_records/{record_id}",
            expected,
        )
        print(f"Updated DNS record: {record_type} {name} -> {expected['content']}")
        return

    client.request("POST", f"zones/{zone_id}/dns_records", expected)
    print(f"Created DNS record: {record_type} {name} -> {expected['content']}")


def build_http_dns_records(
    domain: str,
    ipv4: Optional[str],
    ipv6: Optional[str],
    proxied: bool,
    www_mode: str,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    ttl = 1

    if ipv4:
        records.append(
            {
                "type": "A",
                "name": domain,
                "content": ipv4,
                "proxied": proxied,
                "ttl": ttl,
            }
        )
    if ipv6:
        records.append(
            {
                "type": "AAAA",
                "name": domain,
                "content": ipv6,
                "proxied": proxied,
                "ttl": ttl,
            }
        )

    www_name = f"www.{domain}"
    if www_mode == "same-ip":
        if ipv4:
            records.append(
                {
                    "type": "A",
                    "name": www_name,
                    "content": ipv4,
                    "proxied": proxied,
                    "ttl": ttl,
                }
            )
        if ipv6:
            records.append(
                {
                    "type": "AAAA",
                    "name": www_name,
                    "content": ipv6,
                    "proxied": proxied,
                    "ttl": ttl,
                }
            )
    elif www_mode == "cname":
        records.append(
            {
                "type": "CNAME",
                "name": www_name,
                "content": domain,
                "proxied": proxied,
                "ttl": ttl,
            }
        )

    return records


def get_or_create_zone_ruleset(
    client: CloudflareClient,
    zone_id: str,
    phase: str,
    name: str,
) -> Dict[str, Any]:
    rulesets = client.request("GET", f"zones/{zone_id}/rulesets")
    for ruleset in rulesets:
        if ruleset.get("kind") == "zone" and ruleset.get("phase") == phase:
            return client.request("GET", f"zones/{zone_id}/rulesets/{ruleset['id']}")

    return client.request(
        "POST",
        f"zones/{zone_id}/rulesets",
        {"name": name, "kind": "zone", "phase": phase},
    )


def upsert_ruleset_rule(
    client: CloudflareClient,
    zone_id: str,
    ruleset: Dict[str, Any],
    rule: Dict[str, Any],
) -> None:
    existing_rules = ruleset.get("rules", [])
    ref = rule.get("ref")
    description = rule.get("description")
    for current_rule in existing_rules:
        if ref and current_rule.get("ref") == ref:
            client.request(
                "PATCH",
                f"zones/{zone_id}/rulesets/{ruleset['id']}/rules/{current_rule['id']}",
                rule,
            )
            print(f"Updated Cloudflare rule: {description}")
            return
        if not ref and description and current_rule.get("description") == description:
            client.request(
                "PATCH",
                f"zones/{zone_id}/rulesets/{ruleset['id']}/rules/{current_rule['id']}",
                rule,
            )
            print(f"Updated Cloudflare rule: {description}")
            return

    client.request(
        "POST",
        f"zones/{zone_id}/rulesets/{ruleset['id']}/rules",
        rule,
    )
    print(f"Created Cloudflare rule: {description}")


def ensure_basic_firewall_rule(client: CloudflareClient, zone_id: str) -> None:
    ruleset = get_or_create_zone_ruleset(
        client,
        zone_id,
        "http_request_firewall_custom",
        "ansible-stack-basic-firewall",
    )
    upsert_ruleset_rule(client, zone_id, ruleset, SENSITIVE_PATHS_RULE)


def ensure_canonical_redirect(
    client: CloudflareClient,
    zone_id: str,
    domain: str,
    canonical_host: str,
) -> None:
    if canonical_host == "none":
        return

    if canonical_host == "www":
        source_host = domain
        target_host = f"www.{domain}"
        rule_ref = "redirect_apex_to_www"
        description = "Redirect apex to www"
    else:
        source_host = f"www.{domain}"
        target_host = domain
        rule_ref = "redirect_www_to_apex"
        description = "Redirect www to apex"

    ruleset = get_or_create_zone_ruleset(
        client,
        zone_id,
        "http_request_dynamic_redirect",
        "ansible-stack-canonical-redirect",
    )
    rule = {
        "ref": rule_ref,
        "description": description,
        "expression": f'(http.host eq "{source_host}")',
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "target_url": {
                    "expression": f'concat("https://{target_host}", http.request.uri.path)'
                },
                "status_code": 301,
                "preserve_query_string": True,
            }
        },
        "enabled": True,
    }
    upsert_ruleset_rule(client, zone_id, ruleset, rule)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Configure an existing Cloudflare zone: discover the zone ID, "
            "apply safe zone settings, ensure DNSSEC, create missing HTTP DNS "
            "records, and install a small set of basic rules."
        )
    )
    parser.add_argument("--domain", required=True, help="Root domain / zone name.")
    parser.add_argument("--api-token", help="Cloudflare API token.")
    parser.add_argument("--auth-email", help="Cloudflare account email for Global API key auth.")
    parser.add_argument("--global-api-key", help="Cloudflare Global API key.")
    parser.add_argument("--ipv4", help="IPv4 address for apex/www HTTP records.")
    parser.add_argument("--ipv6", help="IPv6 address for apex/www HTTP records.")
    parser.add_argument(
        "--auto-detect-ip",
        action="store_true",
        help="Attempt to detect public IPv4/IPv6 automatically when not provided.",
    )
    parser.add_argument(
        "--www-mode",
        choices=("cname", "same-ip", "skip"),
        default="cname",
        help="How to handle the www host when it has no HTTP DNS records yet.",
    )
    parser.add_argument(
        "--canonical-host",
        choices=("apex", "www", "none"),
        default="apex",
        help="Install a basic redirect rule for the canonical host.",
    )
    parser.add_argument(
        "--dns-only",
        action="store_true",
        help="Create DNS records as DNS-only instead of proxied through Cloudflare.",
    )
    parser.add_argument(
        "--skip-zone-settings",
        action="store_true",
        help="Skip zone setting updates.",
    )
    parser.add_argument(
        "--skip-dnssec",
        action="store_true",
        help="Skip DNSSEC activation.",
    )
    parser.add_argument(
        "--skip-basic-rules",
        action="store_true",
        help="Skip firewall and canonical redirect rules.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print write operations without sending them to Cloudflare.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show API requests on stderr.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)

    ipv4 = args.ipv4
    ipv6 = args.ipv6

    if args.auto_detect_ip:
        ipv4 = ipv4 or detect_public_ip("https://api.ipify.org")
        ipv6 = ipv6 or detect_public_ip("https://api64.ipify.org")

    client = CloudflareClient(
        api_token=args.api_token,
        auth_email=args.auth_email,
        global_api_key=args.global_api_key,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    zone = get_zone(client, args.domain)
    zone_id = zone["id"]
    print(f"Zone: {zone['name']} ({zone_id})")

    if not args.skip_zone_settings:
        ensure_zone_settings(client, zone_id, DEFAULT_ZONE_SETTINGS)

    if not args.skip_dnssec:
        ensure_dnssec(client, zone_id)

    existing_records = list_dns_records(client, zone_id)
    apex_http_records = [
        record
        for record in existing_records
        if record.get("name") == args.domain and record.get("type") in {"A", "AAAA", "CNAME"}
    ]
    if not ipv4 and not ipv6 and not apex_http_records:
        raise CloudflareError(
            "No IP address available and no existing apex HTTP DNS record found. "
            "Provide --ipv4/--ipv6 or use --auto-detect-ip."
        )

    desired_records = build_http_dns_records(
        domain=args.domain,
        ipv4=ipv4,
        ipv6=ipv6,
        proxied=not args.dns_only,
        www_mode=args.www_mode,
    )
    for record in desired_records:
        ensure_dns_record(client, zone_id, existing_records, record)
        existing_records = list_dns_records(client, zone_id)

    if not args.skip_basic_rules:
        try:
            ensure_basic_firewall_rule(client, zone_id)
        except CloudflareError as exc:
            eprint(f"WARNING: could not configure the basic firewall rule: {exc}")
        try:
            ensure_canonical_redirect(client, zone_id, args.domain, args.canonical_host)
        except CloudflareError as exc:
            eprint(f"WARNING: could not configure the canonical redirect rule: {exc}")

    print("Cloudflare bootstrap completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CloudflareError as exc:
        eprint(f"ERROR: {exc}")
        raise SystemExit(1)
