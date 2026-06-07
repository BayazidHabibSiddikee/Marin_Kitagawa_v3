#!/bin/bash
# setup_throne_room.sh — Configure AI containment "Throne Room"
# Part of Phase 1.2 of the Marin OS Fix Plan

set -e

THRONE="/marin_throne"
MARIN_HOME="/home/marin"

echo "→ Configuring Throne Room at $THRONE..."

# Ensure directories exist
mkdir -p "$THRONE/home/marin"
mkdir -p "$THRONE/etc/marin"
mkdir -p "$THRONE/var/log/marin/failures"
mkdir -p "$THRONE/vault"

# 1. Symlink /home/marin to the Throne Room
if [ -d "$MARIN_HOME" ] && [ ! -L "$MARIN_HOME" ]; then
    echo "  Symlinking $MARIN_HOME -> $THRONE/home/marin"
    # Move existing content
    cp -a "$MARIN_HOME/." "$THRONE/home/marin/"
    rm -rf "$MARIN_HOME"
    ln -s "$THRONE/home/marin" "$MARIN_HOME"
fi

# 2. Configure Marin directory
mkdir -p "$THRONE/usr/share/marin"
if [ -d "/usr/share/marin" ] && [ ! -L "/usr/share/marin" ]; then
    cp -a "/usr/share/marin/." "$THRONE/usr/share/marin/"
    rm -rf "/usr/share/marin"
    ln -s "$THRONE/usr/share/marin" "/usr/share/marin"
fi

# 3. Secure the Audit Log
mkdir -p /var/log/marin_ai_audit
touch /var/log/marin_ai_audit/ai_actions.log
chmod 700 /var/log/marin_ai_audit
chown root:root /var/log/marin_ai_audit/ai_actions.log
chmod 666 /var/log/marin_ai_audit/ai_actions.log
# Note: In a real system, we would use 'chattr +a' here, 
# but we'll stick to permissions for the build environment compatibility.

# 4. Set Ownership
chown -R marin:marin "$THRONE"
# Audit directory is root-owned for integrity
chown root:root /var/log/marin_ai_audit

echo "✓ Throne Room containment configured."
