package llm

import (
	"fmt"
	"io"
	"net/http"
	"strings"
)

const (
	// ProviderGroq and ProviderGemini identify the supported providers.
	ProviderGroq   = "groq"
	ProviderGemini = "gemini"

	// DefaultGroqModel and DefaultGeminiModel are the models used when the
	// --model flag is not provided.
	DefaultGroqModel   = "llama-3.3-70b-versatile"
	DefaultGeminiModel = "gemini-2.5-flash"

	// DefaultGroqTemperature and DefaultGeminiTemperature are the generation
	// temperatures used on the first attempt of each commit cycle.
	DefaultGroqTemperature   = 0.5
	DefaultGeminiTemperature = 0.3

	// MaxCommitLength caps the final commit message length.
	MaxCommitLength = 200

	// maxTemperature is the ceiling for the progressive temperature, so that
	// regenerated suggestions stay coherent.
	maxTemperature = 0.9
	// temperatureStep is added to the temperature on each "Recriar" attempt.
	temperatureStep = 0.2
)

// Provider is the strategy used to generate a commit message from a prompt.
// Concrete implementations are interchangeable (Strategy pattern), enabling
// automatic fallback between providers.
type Provider interface {
	// Name returns the provider identifier (e.g. "groq", "gemini").
	Name() string
	// BaseTemperature returns the default generation temperature used on the
	// first attempt (retry 0), which is escalated per retry via TemperatureFor.
	BaseTemperature() float64
	// GenerateCommit sends the prompt at the given temperature and returns a
	// raw commit suggestion.
	GenerateCommit(prompt string, temperature float64) (string, error)
}

// TemperatureFor returns the generation temperature for the given base and
// retry count. Temperature rises by temperatureStep per retry, capped at
// maxTemperature, so successive "Recriar" attempts produce more varied
// output without becoming incoherent.
func TemperatureFor(base float64, retryCount int) float64 {
	t := base + float64(retryCount)*temperatureStep
	if t > maxTemperature {
		t = maxTemperature
	}
	return t
}

// sendRequest performs an HTTP request and returns the response body.
// Non-200 statuses are converted into explicit errors including the API
// response body for debugging.
func sendRequest(client *http.Client, req *http.Request) ([]byte, error) {
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		b, err := io.ReadAll(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("status code %d: falha ao ler corpo da resposta", resp.StatusCode)
		}
		return nil, fmt.Errorf("status code %d: %s", resp.StatusCode, string(b))
	}
	return io.ReadAll(resp.Body)
}

// CleanOutput normalizes a raw LLM response into a single-line commit message:
// strips quotes/backticks, keeps the first line and enforces MaxCommitLength.
func CleanOutput(s string) string {
	s = strings.NewReplacer(`"`, "", "`", "").Replace(s)
	s = strings.TrimSpace(s)
	if lines := strings.Split(s, "\n"); len(lines) > 0 {
		s = lines[0]
	}
	if len(s) > MaxCommitLength {
		s = s[:MaxCommitLength]
	}
	return s
}
