#!/bin/bash
# migrate_images.sh — Run once during initial deployment to pull CDN assets
# Usage: bash migrate_images.sh

CDN="https://img1.wsimg.com/isteam/ip/ebb9fa42-f145-4b43-a83b-ce49cd96606f"
DEST="app/static/images"
mkdir -p "$DEST"

# Confirmed asset: Jeep Wrangler
wget -q -O "$DEST/jeepWrangler.webp" "$CDN/jeepWrangler.webp"
echo "jeepWrangler.webp: done"

# TODO: Confirm logo filename via DevTools Network tab on live site, then uncomment:
# wget -q -O "$DEST/logo.png" "$CDN/<logo-filename>"
# echo "logo.png: done"

echo ""
echo "Image migration complete."
echo "Note: 6 experience photos (sf_city_icons.jpg, coastal_charm.jpg, wine_country.jpg,"
echo "      hiking_bay.jpg, silicon_valley.jpg, east_bay.jpg) must be added manually to $DEST/"
