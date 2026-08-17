package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/Elliton-Luis/synapse/internal/commit"
	"github.com/Elliton-Luis/synapse/internal/config"
	"github.com/Elliton-Luis/synapse/internal/git"
	"github.com/Elliton-Luis/synapse/internal/llm"
	"github.com/Elliton-Luis/synapse/internal/prompt"
	"github.com/Elliton-Luis/synapse/internal/ui"
)

var errNoChanges = errors.New("Nenhuma alteração no stage. Use 'git add' antes de executar.")

func main() {
	if err := run(); err != nil {
		if errors.Is(err, errNoChanges) {
			ui.Error(err.Error())
			os.Exit(1)
		}
		ui.Fatal(err.Error())
	}
}

func run() error {
	if len(os.Args) >= 2 && os.Args[1] == "lang" {
		return handleLang(os.Args[2:])
	}

	cfg, err := config.Load()
	if err != nil {
		return err
	}

	defaultPattern := prompt.PatternFileEN
	if cfg.Lang == "pt" {
		defaultPattern = prompt.PatternFilePT
	}

	providerFlag := flag.String("provider", "auto", "Força um provedor (groq, gemini, auto)")
	modelFlag := flag.String("model", "", "Sobrescreve o modelo padrão")
	patternFlag := flag.String("pattern", defaultPattern, "Arquivo de padrão a ser lido")
	debugFlag := flag.Bool("debug", false, "Ativa logs detalhados de depuração")
	flag.Parse()

	ui.SetDebug(*debugFlag)

	if err := validateProvider(*providerFlag); err != nil {
		return err
	}
	if err := validateModel(*modelFlag); err != nil {
		return err
	}

	if err := prompt.EnsurePatternFiles(); err != nil {
		return err
	}
	if err := git.EnsureGitignore(); err != nil {
		ui.Debug(fmt.Sprintf("Falha ao atualizar .gitignore: %v", err))
	}

	diff, err := git.GetDiff()
	if err != nil {
		return err
	}
	if diff == "" {
		return errNoChanges
	}

	pattern, err := prompt.LoadPattern(*patternFlag)
	if err != nil {
		return err
	}

	builder := prompt.NewBuilder(pattern, cfg.Lang)
	retryCount := 0

	for {
		currentPrompt := builder.WithDiff(diff).WithRetryCount(retryCount).Build()

		providers, err := buildProviders(cfg, *providerFlag, *modelFlag)
		if err != nil {
			return err
		}

		suggestion, err := generate(providers, currentPrompt, retryCount)
		if err != nil {
			return err
		}
		suggestion = llm.CleanOutput(suggestion)

		ui.Suggestion(suggestion)
		action := ui.Confirm()

		switch action {
		case "y":
			if err := commit.Execute(suggestion); err != nil {
				return fmt.Errorf("falha ao executar o commit: %w", err)
			}
			ui.Success("Commit", "realizado com sucesso.")
			return nil
		case "r":
			retryCount++
		case "n":
			ui.Info("Operação cancelada pelo usuário.")
			return nil
		default:
			ui.Warn("Opção inválida. Use Y, R ou N.")
		}
	}
}

func handleLang(args []string) error {
	if len(args) < 1 {
		return errors.New("Uso: syn lang <en|pt>")
	}
	lang := strings.ToLower(args[0])
	if lang != "en" && lang != "pt" {
		return errors.New("Idioma suportado: en ou pt.")
	}
	if err := config.SetLang(lang); err != nil {
		return fmt.Errorf("falha ao salvar o idioma: %w", err)
	}
	ui.Success("Idioma padrão do Synapse", "alterado para "+strings.ToUpper(lang))
	return nil
}

func validateProvider(provider string) error {
	switch provider {
	case "auto", llm.ProviderGroq, llm.ProviderGemini:
		return nil
	}
	return fmt.Errorf("provedor inválido: %q (valores aceitos: auto, groq, gemini)", provider)
}

var modelPattern = regexp.MustCompile(`^[A-Za-z0-9._:/+-]+$`)

func validateModel(model string) error {
	if model == "" {
		return nil
	}
	if !modelPattern.MatchString(model) {
		return fmt.Errorf("modelo inválido: %q (permitido apenas letras, números e os caracteres '.', '_', ':', '/', '+', '-')", model)
	}
	return nil
}

func buildProviders(cfg *config.Config, provider, model string) ([]llm.Provider, error) {
	switch provider {
	case "auto":
		var providers []llm.Provider
		if cfg.GroqKey != "" {
			providers = append(providers, llm.NewGroq(cfg.GroqKey, resolveModel(model, llm.DefaultGroqModel)))
		}
		if cfg.GeminiKey != "" {
			providers = append(providers, llm.NewGemini(cfg.GeminiKey, resolveModel(model, llm.DefaultGeminiModel)))
		}
		if len(providers) == 0 {
			return nil, errors.New("nenhuma chave de API configurada no ambiente ou no .env")
		}
		return providers, nil
	case llm.ProviderGroq:
		if cfg.GroqKey == "" {
			return nil, errors.New("GROQ_API_KEY não definida")
		}
		return []llm.Provider{llm.NewGroq(cfg.GroqKey, resolveModel(model, llm.DefaultGroqModel))}, nil
	case llm.ProviderGemini:
		if cfg.GeminiKey == "" {
			return nil, errors.New("GEMINI_API_KEY não definida")
		}
		return []llm.Provider{llm.NewGemini(cfg.GeminiKey, resolveModel(model, llm.DefaultGeminiModel))}, nil
	default:
		return nil, fmt.Errorf("provedor desconhecido: %s", provider)
	}
}

func resolveModel(flagModel, def string) string {
	if flagModel != "" {
		return flagModel
	}
	return def
}

func generate(providers []llm.Provider, currentPrompt string, retryCount int) (string, error) {
	ui.ProgressStart()
	defer ui.ProgressClear()

	var lastErr error
	for _, p := range providers {
		ui.Debug("Tentando provider: " + p.Name())

		temperature := llm.TemperatureFor(p.BaseTemperature(), retryCount)
		ui.Debug(fmt.Sprintf("Provider %s: temperatura %.2f (retry %d)", p.Name(), temperature, retryCount))

		suggestion, err := p.GenerateCommit(currentPrompt, temperature)
		if err == nil {
			return suggestion, nil
		}
		lastErr = err
		ui.Debug(fmt.Sprintf("Falha no provider %s: %v", p.Name(), err))
	}
	return "", fmt.Errorf("falha ao gerar a sugestão de commit: todos os providers falharam. Último erro: %v", lastErr)
}
