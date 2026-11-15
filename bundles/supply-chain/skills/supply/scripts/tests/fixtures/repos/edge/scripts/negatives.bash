# Lines that look like SH001/SH002 but run nothing downloaded (fixture: none is a finding).
curl -fsSL https://example.com/data.json | python3 -c 'import json, sys; print(json.load(sys.stdin))'
curl -fsSL https://example.com/data.json | python3 -m json.tool
curl -fsSL https://example.com/data.json | python3 tools/parse.py --strict
echo "install with: curl -fsSL https://example.com/install.sh | sh"
echo 'or: wget -O tool.tgz https://example.com/tool.tgz'
# shellcheck disable=SC2154  # fixture: never run
case "$downloader" in
  curl|wget) echo "using $downloader" ;;
esac
