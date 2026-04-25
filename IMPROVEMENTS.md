# Idempotency & Maintenance Improvements

## Overview
This document describes the improvements made to support safe, repeatable deployments on Ubuntu/Debian systems.

## Key Improvements

### 1. Role Defaults
Each role now has a `defaults/main.yml` with standardized variables:
- `roles/common/defaults/main.yml` - Base packages
- `roles/security/defaults/main.yml` - Firewall/security settings
- `roles/litespeed/defaults/main.yml` - OLS configuration
- `roles/php/defaults/main.yml` - PHP version and packages (dynamic per version)
- `roles/mariadb/defaults/main.yml` - Database settings
- `roles/redis/defaults/main.yml` - Cache service
- `roles/ssl/defaults/main.yml` - SSL/Certbot settings
- `roles/vhost/defaults/main.yml` - Web root paths and permissions

### 2. Idempotency Improvements

#### MariaDB (`roles/mariadb/tasks/main.yml`)
- **Before**: Always ran setup script with `changed_when: true` (marked as always changed)
- **After**: Checks if database exists first, only initializes if missing
- **Benefit**: Subsequent runs skip database initialization when already configured

#### SSL Certificates (`roles/ssl/tasks/main.yml`)
- **Before**: Always attempted to generate certificates with certbot
- **After**: Uses `stat` to check if certificate already exists (`/etc/letsencrypt/live/{{ domain }}/fullchain.pem`)
- **Benefit**: Prevents unnecessary renewal prompts and fails on re-runs

#### Virtual Hosts (`roles/vhost/tasks/main.yml`)
- **Before**: Created config files every run without checking
- **After**: Uses `stat` to check if Nginx/Apache/OLS configs exist before creating
- **After**: Apache `a2ensite` properly detects already-enabled sites
- **Benefit**: Safe to re-run without disrupting live configurations

#### PHP Installation (`roles/php/tasks/main.yml`)
- **Before**: Hardcoded PHP 8.4 and 8.5 packages for OLS only
- **After**: Dynamic PHP version selection based on `php_active` variable; separate packages for OLS vs. Nginx/Apache
- **Benefit**: Supports future PHP versions; doesn't install unnecessary packages

### 3. Ansible Configuration
- **`.ansible-lint`**: Linting rules for code quality
  - Run: `ansible-lint`
  - Enforces consistent task naming, reduces warnings

### 4. Improved Inventory (`inventory.ini`)
- Supports multiple deployment environments (staging, production)
- Examples for different host configurations (SSH ports, custom users)
- Documented with comments for easy expansion
- Use: `ansible-playbook -i inventory.ini -u root -k interactive_full.yml`

## Debugging & Monitoring

### Check if Deployment Already Ran
Re-running the playbook will now show:
- **Unchanged tasks**: `ok` status (not `changed`)
- **Skipped tasks**: `skip` status where conditions prevented execution
- **Changed tasks**: Only actual modifications show as `changed`

### Example Output
```
TASK [mariadb : Initialize application database and user (skip if exists)] ****
skipped: [server] => (item=hostname)  # DB already exists

TASK [ssl : Generate SSL certificate with certbot (skip if exists)] ****
skipped: [server]  # Certificate already present

TASK [vhost : Create Nginx virtual host config (skip if exists)] ****
skipped: [server]  # Config file already exists
```

### Testing Playbook (Dry-Run)
```bash
ansible-playbook -i inventory.ini --user root interactive_full.yml --check
```

### Full Verbose Output
```bash
ansible-playbook -i inventory.ini --user root interactive_full.yml -vv
```

## Best Practices

1. **Run multiple times**: The playbook should safely run multiple times without issues
2. **Check for changes**: Review the `changed` count in the summary to spot unexpected modifications
3. **Monitor services**: After deployment, verify services are running:
   - `systemctl status mariadb`
   - `systemctl status nginx` (or apache2/lshttpd)
   - `systemctl status redis-server`

4. **Lint before deployment**:
   ```bash
   ansible-lint interactive_full.yml
   ```

## Future Enhancements

- [ ] Add handlers for vhost templates (auto-reload on template changes)
- [ ] Support multi-site deployments
- [ ] Add backup tasks before configuration changes
- [ ] Performance profiling tasks
- [ ] Health check tasks (POST-deployment verification)
