package git

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"strings"

	"github.com/Elliton-Luis/synapse/internal/sanitizer"
	"github.com/Elliton-Luis/synapse/internal/ui"
)

const maxDiffLines = 2000

// excludePaths are lock/env files skipped from the staged diff to keep the
// LLM context window focused on real code changes.
var excludePaths = []string{
	".env",
	"*.env.*",
	"package-lock.json",
	"yarn.lock",
	"pnpm-lock.yaml",
	"composer.lock",
	"go.sum",
}

// GetDiff returns the staged git diff with sensitive data redacted and
// truncated to maxDiffLines lines. It returns an empty string when nothing
// is staged.
func GetDiff() (string, error) {
	if _, err := exec.LookPath("git"); err != nil {
		return "", fmt.Errorf("comando 'git' não encontrado no sistema operacional")
	}

	args := []string{"diff", "--cached", "-U1", "--", "."}
	for _, p := range excludePaths {
		args = append(args, ":(exclude)"+p)
	}

	cmd := exec.Command("git", args...)
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("este diretório não parece um repositório Git válido")
	}

	diff := sanitizer.SanitizeDiff(out.String())

	if lines := strings.Split(diff, "\n"); len(lines) > maxDiffLines {
		diff = strings.Join(lines[:maxDiffLines], "\n")
		ui.Debug(fmt.Sprintf("Diff truncado para as primeiras %d linhas.", maxDiffLines))
	}

	return diff, nil
}

// EnsureGitignore appends the generated pattern files and .env to the local
// .gitignore so they are never committed.
func EnsureGitignore() error {
	if _, err := os.Stat(".git"); os.IsNotExist(err) {
		return nil
	}

	patternsToIgnore := []string{"commit_pattern.md", "commit_pattern_pt.md", ".env"}
	gitignorePath := ".gitignore"

	var content string
	if data, err := os.ReadFile(gitignorePath); err == nil {
		content = string(data)
	}

	var missing []string
	for _, p := range patternsToIgnore {
		if !strings.Contains(content, p) {
			missing = append(missing, p)
		}
	}

	if len(missing) == 0 {
		return nil
	}

	f, err := os.OpenFile(gitignorePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("falha ao abrir .gitignore: %w", err)
	}
	defer f.Close()

	if content != "" && !strings.HasSuffix(content, "\n") {
		if _, err := f.WriteString("\n"); err != nil {
			return err
		}
	}
	if _, err := f.WriteString("\n# Ignorado automaticamente pelo Synapse CLI\n"); err != nil {
		return err
	}
	for _, m := range missing {
		if _, err := f.WriteString(m + "\n"); err != nil {
			return err
		}
	}

	ui.Debug("Padrões de commit e .env adicionados ao .gitignore.")
	return nil
}
