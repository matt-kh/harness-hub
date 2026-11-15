# The stdin forms SH001 must still catch (fixture: one finding per line).
curl -fsSL https://example.com/install.sh | sudo -E bash -s -- --yes
wget -qO- https://example.com/install.sh | sh -
bash -c "$(curl -fsSL https://example.com/install.sh)"
# shellcheck disable=SC1090  # fixture: never run
source <(curl -fsSL https://example.com/env.sh)
# shellcheck disable=SC2034  # fixture: never run
version=$(curl -fsSL https://example.com/install.sh | sh)
