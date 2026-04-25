# Multi-Version PHP Implementation Summary

## What Changed

### 1. Interactive Playbook (`interactive_full.yml`)
- **Old**: Single prompt for PHP version (84/85)
- **New**: Single prompt for PHP version (82/83/84/85) with defaults to latest (85)
- Added version validation against available options
- Added deployment summary display
- **Correction**: Installs all 4 versions (8.2.30, 8.3.30, 8.4.20, 8.5.5) simultaneously

### 2. PHP Role (`roles/php/`)

#### Defaults (`defaults/main.yml`)
- **New**: Defined all 4 PHP versions with exact patch versions
- Added computed variables for version formatting
- Created template variables for package management
- **php.ini configuration**: Production-based with optimized settings

#### Tasks (`tasks/main.yml`)
- **New**: Install all 4 PHP versions simultaneously
- Configure php.ini for each version with production settings and extensions
- Automatically generate version-switching configs:
  - **LiteSpeed**: External app processor definitions (one per version)
  - **Nginx**: Upstream definitions with sockets for each version
  - **Apache**: Proxy handler configurations for each version
- Create version-specific shell environment configs
- Create universal `php-switch` script for easy switching

### 3. Web Server Templates

#### Nginx (`nginx_vhost.conf.j2`)
- Updated to use new variable naming (`php_versions_all[php_active].label`)
- Added comments for version switching
- Socket path uses active version by default
- References new upstreams config file

#### Apache (`apache_vhost.conf.j2`)
- Updated to PHP-FPM proxy setup
- Socket path uses active version by default
- Comments show how to switch versions
- References new proxies config file

#### OpenLiteSpeed (`litespeed_vhost.conf.j2`)
- Updated template with new variable naming
- References external app processor
- Links to version switching documentation

### 4. Configuration Generation

All version configs are auto-generated in `/usr/local/etc/php-versions/`:

**LiteSpeed:**
```
82-ols-external-apps.conf, 83-ols-external-apps.conf, 84-ols-external-apps.conf, 85-ols-external-apps.conf
82-ols.conf, 83-ols.conf, 84-ols.conf, 85-ols.conf
```

**Nginx:**
```
php-nginx-upstreams.conf         # All upstream definitions
82-nginx.conf, 83-nginx.conf, 84-nginx.conf, 85-nginx.conf
```

**Apache:**
```
php-apache-proxies.conf          # All proxy definitions
82-apache.conf, 83-apache.conf, 84-apache.conf, 85-apache.conf
```

## Deployment Example

```bash
$ ansible-playbook -i inventory.ini interactive_full.yml

Domain: example.com
Server type (ols/nginx/apache): nginx
PHP version (82/83/84/85) [85]: 85
Database name: wp_db
Database user: wp_user
Database password: ****
WordPress table prefix (wp_): wp_

=== Deployment Configuration ===
Domain: example.com
Server Type: nginx
PHP Version: PHP 8.5.5 (all versions will be installed)
Active PHP Version: 85
Database: wp_db
WordPress Prefix: wp_
```

What gets installed:
- PHP 8.2.30, 8.3.30, 8.4.20, 8.5.5 (all 4 versions)
- Nginx configured to use 8.5.5 by default
- Config files for switching to any of the 4 versions

## Version Switching Workflow

### On First Deployment:
1. All 4 PHP versions are installed and configured
2. Active version is set in web server configuration
3. Version switching configs are generated

### To Switch Versions:
1. Use `php-switch <version> [server_type]` script
2. Or manually update web server config to use different socket/processor
3. Reload web server

### PHP Configuration Details:
- **Base**: php.ini-production for each version
- **Performance**: OPcache with JIT enabled, optimized memory settings
- **Limits**: 512M memory, 300s execution time, 256M upload size
- **Extensions**: Redis, mbstring, xml, zip, intl, bcmath, PDO drivers, etc.
- **Timezone**: Europe/Prague
2. Active version (selected) is configured in vhost
3. Switching configs are generated in `/usr/local/etc/php-versions/`

### To Switch Versions Later:
1. Edit vhost config to use different socket/processor
2. Reload web server
3. Test with `curl` or browser

**For LiteSpeed example:**
```bash
# Edit /usr/local/lsws/conf/vhosts/example.com.conf
# Change context from:  extprocessor lsphp84_0
#               to:  extprocessor lsphp84_1
systemctl reload lshttpd
```

**For Nginx example:**
```bash
# Edit /etc/nginx/sites-available/example.com
# Change fastcgi_pass from: phpfpm_84_0
#                     to: phpfpm_84_1
systemctl reload nginx
```

## Key Files Modified

| File | Purpose |
|------|---------|
| `interactive_full.yml` | Split PHP version into major/minor prompts |
| `roles/php/defaults/main.yml` | Added version definitions & templates |
| `roles/php/tasks/main.yml` | Major expansion: install all versions + generate configs |
| `roles/vhost/templates/nginx_vhost.conf.j2` | Updated for PHP-FPM sockets |
| `roles/vhost/templates/apache_vhost.conf.j2` | Updated for PHP-FPM proxies |
| `roles/vhost/templates/litespeed_vhost.conf.j2` | Created (was inline) |
| `roles/vhost/tasks/main.yml` | Now uses template for OLS |

## New Documentation

- `PHP_VERSIONS.md`: Complete guide to multi-version PHP setup & switching
- Version switching configs in `/usr/local/etc/php-versions/` (auto-generated)

## Benefits

✅ **Easy Version Management**: All minors installed, switch on-demand
✅ **No Reinstallation**: Just config file edits + reload
✅ **Testing & Gradual Migration**: Test new version before full cutover
✅ **Isolated Processes**: Each PHP version runs in its own socket
✅ **Web-Server-Agnostic**: Works with OLS, Nginx, Apache
✅ **Automatic Config Generation**: Configs ready without manual editing
