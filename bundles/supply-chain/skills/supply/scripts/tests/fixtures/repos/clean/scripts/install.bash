set -eu
curl -fsSL -o tool.tgz https://example.com/tool-1.2.3.tgz
echo "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  tool.tgz" | sha256sum -c -
go install example.com/tool@v1.2.3
cargo install ripgrep --version 14.1.1 --locked
curl -fsS https://example.com/healthz -o /dev/null
