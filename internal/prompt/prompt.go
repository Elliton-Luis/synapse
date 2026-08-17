package prompt

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/Elliton-Luis/synapse/internal/ui"
)

const (
	// PatternFileEN and PatternFilePT are the pattern files managed in the
	// working directory.
	PatternFileEN = "commit_pattern.md"
	PatternFilePT = "commit_pattern_pt.md"
)

const defaultPatternEN = `Strictly follow the Conventional Commits specification.
Allowed types: feat, fix, docs, test, build, perf, style, refactor, chore, ci, raw, cleanup, remove.

MANDATORY RULES:
1. Write the entire commit message in ENGLISH.
2. Use the IMPERATIVE mood (e.g., "add feature" not "added feature").
3. Format strictly as: <type>(<optional scope>): <description>
4. Keep the description short, personal, and precise.
5. Examples of good commits:
   - feat(auth): add JWT validation middleware
   - fix: resolve null pointer in user config
   - refactor(api): switch to native http client
6. Return ONLY the final commit message string. Do not use markdown blocks, backticks, or quotes.`

const defaultPatternPT = `Siga estritamente a especificação do Conventional Commits.
Tipos permitidos: feat, fix, docs, test, build, perf, style, refactor, chore, ci, raw, cleanup, remove.

REGRAS OBRIGATÓRIAS:
1. Escreva toda a mensagem em PORTUGUÊS.
2. Use o tempo verbal IMPERATIVO (ex: "adicione recurso" em vez de "adicionou recurso").
3. Formate estritamente como: <tipo>(<escopo opcional>): <descrição>
4. Mantenha a descrição curta, pessoal e precisa.
5. Exemplos de bons commits:
   - feat(auth): adicione middleware de validação JWT
   - fix: corrija erro de ponteiro nulo na config
   - refactor(api): altere para cliente http nativo
6. Retorne APENAS a mensagem final do commit. Não use blocos de código markdown, crases ou aspas.`

// DefaultPattern returns the built-in commit pattern for the given language.
func DefaultPattern(lang string) string {
	if lang == "pt" {
		return defaultPatternPT
	}
	return defaultPatternEN
}

// EnsurePatternFiles writes the built-in pattern files to the working
// directory when they are missing.
func EnsurePatternFiles() error {
	if err := ensurePatternFile(PatternFileEN, defaultPatternEN); err != nil {
		return err
	}
	return ensurePatternFile(PatternFilePT, defaultPatternPT)
}

func ensurePatternFile(name, content string) error {
	if _, err := os.Stat(name); os.IsNotExist(err) {
		if err := os.WriteFile(name, []byte(content), 0644); err != nil {
			return fmt.Errorf("falha ao criar %s: %w", name, err)
		}
		ui.Debug("Arquivo " + name + " criado com sucesso.")
	}
	return nil
}

// LoadPattern reads a commit pattern file from the working directory. It
// returns an explicit error when the file does not exist, instead of
// silently falling back to a hardcoded pattern.
func LoadPattern(filename string) (string, error) {
	pwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("falha ao obter diretório atual: %w", err)
	}

	path := filepath.Join(pwd, filename)
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("arquivo de padrão não encontrado em %s", path)
	}

	ui.Debug("Padrão de commit carregado com sucesso de: " + path)
	return string(data), nil
}

// Builder composes the system prompt sent to the LLM providers.
type Builder struct {
	pattern    string
	lang       string
	diff       string
	retryCount int
}

// NewBuilder creates a prompt builder for the given commit pattern and
// language ("pt" or "en").
func NewBuilder(pattern, lang string) *Builder {
	return &Builder{pattern: pattern, lang: lang}
}

// WithDiff sets the (sanitized) git diff to analyze.
func (b *Builder) WithDiff(diff string) *Builder {
	b.diff = diff
	return b
}

// WithRetryCount sets how many previous suggestions the user rejected, so
// the prompt asks for a different commit message.
func (b *Builder) WithRetryCount(n int) *Builder {
	b.retryCount = n
	return b
}

// Build returns the final prompt for the configured pattern, diff and retry
// count, including the per-language formatting safety lock.
func (b *Builder) Build() string {
	base := fmt.Sprintf("Padrão exigido:\n%s\n\nAnalise o seguinte git diff:\n%s\n\n%s",
		b.pattern, b.diff, safetyLock(b.lang))

	if b.retryCount > 0 {
		if b.lang == "pt" {
			base += fmt.Sprintf("\n\nO usuário rejeitou as %d sugestões anteriores. Gere uma mensagem de commit diferente das anteriores.", b.retryCount)
		} else {
			base += fmt.Sprintf("\n\nUser rejected the previous %d suggestions. Generate a different commit message.", b.retryCount)
		}
	}
	return base
}

func safetyLock(lang string) string {
	if lang == "pt" {
		return "ATENCAO: REGRA CRITICA DE FORMATACAO\n" +
			"Você DEVE retornar a mensagem ESTRITAMENTE no formato:\n" +
			"tipo: descrição curta\n" +
			"OU\n" +
			"tipo(escopo): descrição curta\n\n" +
			"NUNCA esqueça os dois pontos (:) após o tipo/escopo. A mensagem inteira DEVE estar em PORTUGUÊS. Não use aspas, crases ou blocos markdown."
	}
	return "ATTENTION: CRITICAL FORMATTING RULE\n" +
		"You MUST return the message STRICTLY in the format:\n" +
		"type: short description\n" +
		"OR\n" +
		"type(scope): short description\n\n" +
		"NEVER forget the colon (:) after the type/scope. The entire message MUST be in ENGLISH. Do not use quotes, backticks, or markdown blocks."
}
