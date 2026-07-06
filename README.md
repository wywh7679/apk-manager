# APK Manager

A small PHP 7.4 application for maintaining a JSON-backed directory of links.

## Features

- Public directory view with category filtering.
- Authenticated management pages for items and categories.
- Item fields for title, description, URL, category assignments, and display order.
- JSON storage under `data/`.
- CSRF protection on management forms.

## IIS/PHP setup

1. Deploy the repository to an IIS site configured for PHP 7.4.
2. Ensure the IIS application pool identity can read and write the `data/` directory.
3. Set these environment variables for the site:
   - `APK_MANAGER_ADMIN_USER` for the administrator username.
   - `APK_MANAGER_ADMIN_PASSWORD_HASH` for the administrator password hash.
   - `APK_MANAGER_APP_NAME` to customize the displayed application name.
4. Generate a password hash with PHP:

   ```powershell
   php -r "echo password_hash('your-strong-password', PASSWORD_DEFAULT), PHP_EOL;"
   ```

If no environment variables are set, the development login is `admin` / `change-me`. Change this before publishing the site.
