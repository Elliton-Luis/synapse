package sanitizer

import (
	"regexp"
	"strings"
)

var (
	reIndex      = regexp.MustCompile(`(?m)^index [0-9a-fA-F]+\.\.[0-9a-fA-F]+.*$\n?`)
	reMode       = regexp.MustCompile(`(?m)^(old|new) mode [0-9]+$\n?`)
	reCreds      = regexp.MustCompile(`(?i)(access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|secret[_-]?key|api[_-]?key|authorization|password|secret|token)\b(\s*[:=]\s*)(['"][^'"]*['"]|[^\s,;]+)`)
	reBearer     = regexp.MustCompile(`(?i)\bbearer\s+(['"][^'"]*['"]|[A-Za-z0-9._~+/=-]+)`)
	rePrivateKey = regexp.MustCompile(`(?ms)-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----`)
	reEmptyLines = regexp.MustCompile(`\n{3,}`)
)

// SanitizeDiff removes Git metadata and redacts sensitive data (API keys,
// passwords, tokens, private keys, bearer credentials) from a git diff
// before it is sent to an LLM provider.
func SanitizeDiff(diff string) string {
	diff = rePrivateKey.ReplaceAllString(diff, "[REDACTED PRIVATE KEY]")
	diff = reBearer.ReplaceAllString(diff, "[REDACTED]")
	diff = reCreds.ReplaceAllString(diff, "$1$2[REDACTED]")
	diff = reIndex.ReplaceAllString(diff, "")
	diff = reMode.ReplaceAllString(diff, "")
	diff = reEmptyLines.ReplaceAllString(diff, "\n\n")
	return strings.TrimSpace(diff)
}
