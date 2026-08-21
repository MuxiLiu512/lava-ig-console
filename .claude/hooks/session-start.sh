#!/bin/bash
# Install the shared skill packs (gstack + grill-me) for this repo.
#
# Only runs in Claude Code on the web. Those containers are ephemeral and start
# from a fresh clone, so anything installed under ~/.claude dies with the
# session — the skills have to be laid down again on every new container. On a
# laptop the skills are already installed globally, so we stay out of the way.
#
# Never fails the session: a broken bootstrap warns and exits 0. Losing /review
# is annoying; losing the session is worse.
#
# Escape hatch: SKIP_SKILL_BOOTSTRAP=1
set -uo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
[ "${SKIP_SKILL_BOOTSTRAP:-0}" = "1" ] && exit 0

SKILLS="$HOME/.claude/skills"
GSTACK="$SKILLS/gstack"

warn() { echo "session-start: $*" >&2; }

# ── grill-me — a single SKILL.md, so just drop it in ──────────────────────
if [ ! -f "$SKILLS/grill-me/SKILL.md" ]; then
  tmp=$(mktemp -d)
  if git clone --depth 1 -q https://github.com/gusinov/grill-me "$tmp/g" 2>/dev/null; then
    mkdir -p "$SKILLS/grill-me"
    cp "$tmp/g/grill-me/SKILL.md" "$SKILLS/grill-me/SKILL.md"
  else
    warn "grill-me clone failed — skipping"
  fi
  rm -rf "$tmp"
fi


# ── gstack ────────────────────────────────────────────────────────────────
[ -d "$GSTACK/bin" ] && exit 0

if ! command -v bun >/dev/null 2>&1; then
  warn "bun not found — skipping gstack"
  exit 0
fi

mkdir -p "$SKILLS"
if ! git clone --single-branch --depth 1 -q https://github.com/garrytan/gstack.git "$GSTACK" 2>/dev/null; then
  warn "gstack clone failed — skipping"
  rm -rf "$GSTACK"
  exit 0
fi

# gstack's setup shells out to `playwright install chromium`, which this
# environment's egress proxy rejects (cdn.playwright.dev is not on the
# allowlist). The image already ships a Chromium under PLAYWRIGHT_BROWSERS_PATH,
# just at a different revision than gstack's playwright asks for — so point the
# expected revision at the build we already have. Without this, setup aborts
# before it registers a single skill.
shim_chromium() {
  local root="${PLAYWRIGHT_BROWSERS_PATH:-}" want have shell
  [ -n "$root" ] && [ -d "$root" ] || return 0

  want=$(node -e "console.log(require('$GSTACK/node_modules/playwright-core/browsers.json').browsers.find(b=>b.name==='chromium').revision)" 2>/dev/null) || return 0
  [ -n "$want" ] || return 0
  [ -e "$root/chromium-$want" ] && return 0   # the real build is already there

  have=$(ls -d "$root"/chromium-[0-9]* 2>/dev/null | head -1)
  [ -n "$have" ] || return 0

  mkdir -p "$root/chromium-$want"
  ln -sfn "$have/chrome-linux" "$root/chromium-$want/chrome-linux"
  touch "$root/chromium-$want/INSTALLATION_COMPLETE" "$root/chromium-$want/DEPENDENCIES_VALIDATED"

  # Headless launches use a separate binary, and its layout changed: older
  # builds ship chrome-linux/headless_shell, newer ones expect
  # chrome-headless-shell-linux64/chrome-headless-shell.
  shell=$(ls -d "$root"/chromium_headless_shell-[0-9]* 2>/dev/null | head -1)
  [ -n "$shell" ] || return 0
  [ -e "$shell/chrome-linux/chrome-headless-shell" ] ||
    ln -sfn headless_shell "$shell/chrome-linux/chrome-headless-shell"
  mkdir -p "$root/chromium_headless_shell-$want"
  ln -sfn "$shell/chrome-linux" "$root/chromium_headless_shell-$want/chrome-headless-shell-linux64"
  touch "$root/chromium_headless_shell-$want/INSTALLATION_COMPLETE" \
        "$root/chromium_headless_shell-$want/DEPENDENCIES_VALIDATED"
}

# browsers.json only exists once deps are installed, so install before shimming.
( cd "$GSTACK" && bun install --frozen-lockfile || bun install ) >/dev/null 2>&1 || true
shim_chromium

# --no-team: team mode installs an auto-update hook, which buys nothing here —
# every container clones a fresh copy anyway.
if ! ( cd "$GSTACK" && ./setup --host claude --no-prefix --no-team --no-plan-tune-hooks -q </dev/null ) >/dev/null 2>&1; then
  warn "gstack setup reported errors — some skills may be unavailable"
fi

exit 0
