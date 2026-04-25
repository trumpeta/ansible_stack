# ansible_stack

`ansible_stack` is an Ansible-based bootstrap for a fresh Debian or Ubuntu server that will host a PHP application or a WordPress site behind OpenLiteSpeed, Nginx, or Apache. The project aims at repeatable first-run provisioning with a stronger focus on idempotence, predictable filesystem layout, and safer defaults for production-like environments.

## What It Configures

The main playbook is [interactive_full.yml](/C:/Users/Petr/Documents/GitHub/ansible_stack/interactive_full.yml:1). It prompts for the target domain, preferred web server, active PHP branch, and database credentials, then configures the host.

Configured services and components:

- OpenLiteSpeed, Nginx, or Apache as the HTTP server
- Multi-version PHP for the last four discovered PHP 8 minor branches
- PHP-FPM for Nginx and Apache
- MariaDB
- Redis
- UFW
- fail2ban
- Certbot
- WordPress core bootstrap and `wp-config.php` wiring

## PHP Version Strategy

The playbook discovers the latest PHP releases from the official `php.net` release catalog and selects the latest patch release for the newest four PHP 8 minor branches. Package installation uses only the major-minor package names, so the package manager still resolves the latest patch version available in the configured repository.

If the online lookup fails, the playbook falls back to a bundled version map so the run does not fail just because `php.net` is temporarily unavailable.

## Filesystem Layout

The virtual host layout is now explicit:

- Site root: `/var/www/<domain>`
- Vhost root: `/var/www/<domain>/current`
- Document root: `/var/www/<domain>/current/document_root`

For OpenLiteSpeed the generated vhost config uses `vhRoot` plus `$VH_ROOT/document_root`. For Nginx and Apache the same filesystem path is used directly as the web root.

## Ownership and Permissions

The playbook creates and normalizes the document root with explicit ownership and modes:

- Site root and vhost root directories: `www-data:www-data`, `0755`
- Document root directories: `www-data:www-data`, `0755`
- Regular files inside the document root: `www-data:www-data`, `0644`
- `wp-config.php`: `www-data:www-data`, `0640`

This keeps the served tree readable by the web server while tightening the most sensitive WordPress configuration file.

## Cloudflare Bootstrap

Cloudflare configuration is intentionally kept separate from the server provisioning flow.

Available entry points:

- Standalone script: [scripts/cloudflare_zone_bootstrap.py](/C:/Users/Petr/Documents/GitHub/ansible_stack/scripts/cloudflare_zone_bootstrap.py:1)
- Ansible wrapper playbook: [cloudflare_zone_bootstrap.yml](/C:/Users/Petr/Documents/GitHub/ansible_stack/cloudflare_zone_bootstrap.yml:1)

What the Cloudflare bootstrap does:

- Resolves the existing zone ID by domain through the Cloudflare API
- Applies a small set of safe zone settings
- Tries to enable DNSSEC
- Scans existing DNS records
- Creates missing HTTP DNS records for the apex host
- Creates `www` as either a `CNAME`, matching `A`/`AAAA`, or skips it entirely
- Adds a basic firewall rule for sensitive paths
- Optionally adds a canonical host redirect rule

The script uses only Python standard library modules and supports either an API token or the older email plus Global API key combination.

Example direct usage on Linux:

```bash
python3 scripts/cloudflare_zone_bootstrap.py \
  --domain example.com \
  --api-token "$CF_API_TOKEN" \
  --ipv4 203.0.113.10 \
  --ipv6 2001:db8::10 \
  --canonical-host apex \
  --www-mode cname
```

Dry run example:

```bash
python3 scripts/cloudflare_zone_bootstrap.py \
  --domain example.com \
  --api-token "$CF_API_TOKEN" \
  --auto-detect-ip \
  --dry-run
```

Wrapper playbook example:

```bash
ansible-playbook cloudflare_zone_bootstrap.yml
```

## Main Playbook Usage

Typical interactive run:

```bash
ansible-playbook -i inventory.ini interactive_full.yml
```

The playbook expects Debian or Ubuntu on the managed host and installs the repository prerequisites required for the selected web server and PHP runtime layout.

## Notes

- The repository still contains older reference notes in `PHP_VERSIONS.md` and `MULTIVERSION_PHP_SUMMARY.md`. Those documents are historical context, not the current source of truth.
- The local workstation used for development may not have `ansible-playbook` installed. In that case, validation has to happen on a Linux host or CI runner with Ansible available.
