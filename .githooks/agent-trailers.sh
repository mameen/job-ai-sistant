# Shared helpers — sourced by prepare-commit-msg and commit-msg.
# Blocks/strips AI agent co-author trailers (Cursor, Claude Code, Anthropic).

# One regex for Co-authored-by lines from known agents (case-insensitive).
_AGENT_COAUTHOR_RE='^[Cc]o-[Aa]uthored-[Bb]y:.*(cursor|cursoragent|claude|anthropic|noreply@anthropic)'

# Marketing / attribution fluff some tools append.
_AGENT_FLAFF_RE='^(🤖[[:space:]]*)?[Gg]enerated with.*[Cc]laude'

strip_agent_trailers() {
    # Usage: strip_agent_trailers <commit-msg-file>
    _msg="$1"
    _tmp="$(mktemp "${TMPDIR:-/tmp}/git-commit-msg.XXXXXX")" || return 1
    _kept="$(mktemp "${TMPDIR:-/tmp}/git-commit-kept.XXXXXX")" || { rm -f "$_tmp"; return 1; }

    grep -viE "$_AGENT_COAUTHOR_RE|$_AGENT_FLAFF_RE" "$_msg" > "$_kept" || true

    # Trim trailing blank lines (portable — no GNU sed).
    awk 'NF{p=1} p' "$_kept" > "$_tmp"
    mv "$_tmp" "$_kept"
    cp "$_kept" "$_msg"
    rm -f "$_kept"
}

has_agent_trailers() {
    # Usage: has_agent_trailers <commit-msg-file>  → exit 0 if found
    grep -qiE "$_AGENT_COAUTHOR_RE|$_AGENT_FLAFF_RE" "$1"
}
