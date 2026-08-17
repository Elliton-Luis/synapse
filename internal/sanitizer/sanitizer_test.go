package sanitizer

import "testing"

func TestSanitizeDiffExpanded(t *testing.T) {
	cases := []struct{ name, in, want string }{
		{"private_key", "PRIVATE_KEY=supersecret", "PRIVATE_KEY=[REDACTED]"},
		{"api_key", "X_API_KEY=abc123", "X_API_KEY=[REDACTED]"},
		{"access_token", "access_token = foobar", "access_token = [REDACTED]"},
		{"refresh_token", "refresh_token=xyz", "refresh_token=[REDACTED]"},
		{"client_secret", "client_secret=abc", "client_secret=[REDACTED]"},
		{"bearer_header", "Authorization: Bearer eyJhbGciOi", "Authorization: [REDACTED]"},
		{"ssh_key", "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----", "[REDACTED PRIVATE KEY]"},
		{"ssh_rsa", "-----BEGIN RSA PRIVATE KEY-----\nBBBB\n-----END RSA PRIVATE KEY-----", "[REDACTED PRIVATE KEY]"},
		{"password", `password = "hunter2"`, `password = [REDACTED]`},
		{"index_line", "index 111222..333444 100644\n+code", "+code"},
		{"mode_line", "new mode 100755\n+code", "+code"},
		{"camel_case", "apiKey: secretval", "apiKey: [REDACTED]"},
		{"secret_underscore", "SECRET_KEY=abc", "SECRET_KEY=[REDACTED]"},
	}
	for _, c := range cases {
		if got := SanitizeDiff(c.in); got != c.want {
			t.Errorf("%s: SanitizeDiff(%q) = %q, want %q", c.name, c.in, got, c.want)
		}
	}
}
