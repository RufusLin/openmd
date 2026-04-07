# Add these functions to your .zshrc for markdown preview
localmd() {
    $MD_VIEWER_PY $MD_VIEWER_SCRIPT "$@" >/dev/null 2>&1 &
}
remotemd() {
    local remote_path="$1"
    local filename=$(basename "$remote_path")
    local tmp_file="/tmp/remote_preview_${filename}.md"

    # Pull via the 'home' alias, then launch
    scp "home:$remote_path" "$tmp_file" && \
    $MD_VIEWER_PY $MD_VIEWER_SCRIPT "$tmp_file" >/dev/null 2>&1 &
}