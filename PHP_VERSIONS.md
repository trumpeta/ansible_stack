# Multi-Version PHP Support

## Overview

The ansible_stack now supports installing **all 4 latest PHP 8.x versions** simultaneously, with easy switching between versions. This provides maximum flexibility for testing and production deployments.

## Features

- **Install All 4 Versions**: PHP 8.2.30, 8.3.30, 8.4.20, and 8.5.5 are installed automatically
- **Easy Version Switching**: Switch between installed versions using version-specific configs
- **Web-Server-Agnostic**: Works with OLS, Nginx, and Apache
- **Pre-configured Switching**: Configs for each version are automatically generated
- **Socket-Based**: Each PHP version runs in its own socket for isolation
- **Optimized php.ini**: Each version configured with production settings and common extensions

## Installation & Configuration

### Interactive Prompts

When running `ansible-playbook interactive_full.yml`, you'll see:

```
Domain: example.com
Server type (ols/nginx/apache): ols
PHP version (82/83/84/85) [85]: 85
Database name: wordpress_db
...
```

**What gets installed:**
- **All 4 versions** are installed: PHP 8.2.30, 8.3.30, 8.4.20, 8.5.5
- Selected version becomes the **active** version in vhost configuration
- All versions are ready to switch to without reinstalling

### Version Definition

Available versions are defined in `roles/php/defaults/main.yml`:

```yaml
php_versions_all:
  "82":
    label: "PHP 8.2.30"
    version: "8.2"
    patch: "30"
  "83":
    label: "PHP 8.3.30"
    version: "8.3"
    patch: "30"
  "84":
    label: "PHP 8.4.20"
    version: "8.4"
    patch: "20"
  "85":
    label: "PHP 8.5.5"
    version: "8.5"
    patch: "5"
```

### PHP Configuration

Each installed PHP version gets:
- **php.ini** based on `php.ini-production` with optimized settings:
  - `max_execution_time = 300`
  - `max_input_time = 300`
  - `max_input_vars = 20000`
  - `memory_limit = 512M`
  - `post_max_size = 256M`
  - `upload_max_filesize = 256M`
  - `date.timezone = Europe/Prague`
  - Full OPcache configuration with JIT enabled
- **Common extensions enabled**: Redis, mbstring, xml, zip, intl, bcmath, soap, PDO drivers, etc.
- **CLI and FPM** configurations synchronized

## Switching Between Versions

### Method 1: Using Configuration Files (Recommended)

All switching configs are in `/usr/local/etc/php-versions/`:

#### OpenLiteSpeed

1. View available external app configs:
   ```bash
   cat /usr/local/etc/php-versions/84-ols-external-apps.conf
   ```

2. Add the desired external processor to `/usr/local/lsws/conf/httpd_config.conf`
   - Copy the `<extprocessor lsphp84_0>` block for PHP 8.4.0
   - Copy the `<extprocessor lsphp84_1>` block for PHP 8.4.1, etc.

3. In your vhost config, change the context mapping:
   ```
   <context /php>
     location              /php
     handler               lsapi
     extprocessor          lsphp84_0  # Change from 0 to 1, 2, etc.
   </context>
   ```

4. Reload LiteSpeed:
   ```bash
   systemctl reload lshttpd
   ```

#### Nginx

1. Include upstream configs in your vhost:
   ```nginx
   include /usr/local/etc/php-versions/84-nginx-upstreams.conf;
   ```

2. Change the fastcgi_pass in PHP location:
   ```nginx
   location ~ \.php$ {
       fastcgi_pass phpfpm_84_0;  # Change from 0 to 1, 2, etc.
   }
   ```

3. Reload Nginx:
   ```bash
   systemctl reload nginx
   ```

#### Apache

1. Include proxy configs in your vhost:
   ```apache
   Include /usr/local/etc/php-versions/84-apache-proxies.conf
   ```

2. Change the socket path in PHP handler:
   ```apache
   <FilesMatch \.php$>
       SetHandler "proxy:unix:/var/run/php/php84-fpm-0.sock|fcgi://localhost"
   </FilesMatch>
   ```

3. Reload Apache:
   ```bash
   systemctl reload apache2
   ```

### Method 2: Using Environment Configs

Shell configs are also available at `/usr/local/etc/php-versions/`:
- `84-0-ols.conf`, `84-1-ols.conf` for OpenLiteSpeed
- `84-0-nginx.conf`, `84-1-nginx.conf` for Nginx
- `84-0-apache.conf`, `84-1-apache.conf` for Apache

Source a config to set environment variables:
```bash
source /usr/local/etc/php-versions/84-0-ols.conf
echo $EXTPROCESSOR  # lsphp84_0
echo $PHP_VERSION   # 8.4.0
```

## Generated Configuration Files

After deployment, check `/usr/local/etc/php-versions/` for:

| File | Purpose |
|------|---------|
| `84-ols-external-apps.conf` | LiteSpeed external processor definitions |
| `84-nginx-upstreams.conf` | Nginx upstream definitions (one per minor version) |
| `84-apache-proxies.conf` | Apache proxy/handler configurations |
| `84-{0,1,2}-{ols,nginx,apache}.conf` | Version-specific env configs |

## Available Socket Paths

When all versions are installed, sockets are available at:

```
# OpenLiteSpeed
/usr/local/lsws/lsphp84/bin/lsphp  (symlink or single version)

# Nginx/Apache PHP-FPM
/var/run/php/php84-fpm.sock         (default/latest minor)
/var/run/php/php84-fpm-0.sock       (PHP 8.4.0 if available)
/var/run/php/php84-fpm-1.sock       (PHP 8.4.1 if available)
/var/run/php/php84-fpm-2.sock       (PHP 8.4.2 if available)
```

## Debugging

### Check installed PHP versions:
```bash
# OLS
ls -la /usr/local/lsws/lsphp84/bin/

# Nginx/Apache
php84 -v
php85 -v
ls -la /var/run/php/ | grep php
```

### Check which version is currently active:
```bash
# Nginx - check config
grep "fastcgi_pass" /etc/nginx/sites-available/<domain>

# Apache - check config
grep "SetHandler" /etc/apache2/sites-available/<domain>.conf

# OLS - check config
grep "extprocessor" /usr/local/lsws/conf/vhosts/<domain>.conf
```

### Test PHP version:
```bash
# If you have SSH to server, test active version:
curl http://your-domain/phpinfo.php

# Or create a test file:
echo '<?php phpinfo(); ?>' > /var/www/your-domain/current/test.php
curl http://your-domain/test.php
```

## Performance Considerations

- Each PHP-FPM version runs in its own process pool (isolated)
- OLS handles multiple PHP versions via external processor definitions
- Switching versions requires web server reload, not restart
- No data loss when switching versions

## Future Enhancements

- [ ] Automated version detection from Debian/Ubuntu repos
- [ ] Quick-switch script (`php-switch 84 1 ols`)
- [ ] Health check between version switches
- [ ] Load balancing across multiple versions (for gradual migration)
- [ ] Automatic cleanup of unused minor versions
