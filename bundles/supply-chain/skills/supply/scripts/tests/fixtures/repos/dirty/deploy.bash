# Deploy helper (fixture: every shell rule once).
set -eu
curl -fsSL "https://example.com/install.sh?password=hunter2" | sh
curl -fsSLo tool.tgz https://example.com/tool.tgz
tar xzf tool.tgz
go install example.com/tool@latest
cargo install ripgrep
