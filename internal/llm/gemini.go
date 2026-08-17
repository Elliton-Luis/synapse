package llm

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

const geminiURL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

type geminiPart struct {
	Text string `json:"text"`
}

type geminiContent struct {
	Parts []geminiPart `json:"parts"`
}

type geminiPayload struct {
	Contents          []geminiContent `json:"contents"`
	GenerationConfig  geminiGenConfig `json:"generationConfig"`
	SystemInstruction geminiContent   `json:"systemInstruction"`
}

type geminiGenConfig struct {
	Temperature     float64 `json:"temperature"`
	MaxOutputTokens int     `json:"maxOutputTokens"`
}

// Gemini is a Provider implementation backed by the Gemini API.
type Gemini struct {
	apiKey string
	model  string
}

// NewGemini creates a Gemini provider. The model may be empty, in which case
// DefaultGeminiModel is used by the caller.
func NewGemini(apiKey, model string) *Gemini {
	return &Gemini{apiKey: apiKey, model: model}
}

func (g *Gemini) Name() string { return ProviderGemini }

// BaseTemperature returns the default Gemini generation temperature.
func (g *Gemini) BaseTemperature() float64 { return DefaultGeminiTemperature }

func (g *Gemini) GenerateCommit(prompt string, temperature float64) (string, error) {
	bodyData := geminiPayload{
		Contents: []geminiContent{
			{Parts: []geminiPart{{Text: prompt}}},
		},
		GenerationConfig: geminiGenConfig{
			Temperature:     temperature,
			MaxOutputTokens: 500,
		},
		SystemInstruction: geminiContent{
			Parts: []geminiPart{{Text: "You are a strict Git commit message generator. Return ONLY the final commit message. No quotes, no markdown, no explanations."}},
		},
	}

	jsonData, err := json.Marshal(bodyData)
	if err != nil {
		return "", fmt.Errorf("gemini: falha ao serializar payload: %w", err)
	}

	url := fmt.Sprintf(geminiURL+"?key=%s", g.model, g.apiKey)
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return "", fmt.Errorf("gemini: falha ao criar request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 12 * time.Second}
	respBody, err := sendRequest(client, req)
	if err != nil {
		return "", err
	}

	var res struct {
		Candidates []struct {
			Content struct {
				Parts []struct {
					Text string `json:"text"`
				} `json:"parts"`
			} `json:"content"`
		} `json:"candidates"`
	}
	if err := json.Unmarshal(respBody, &res); err != nil {
		return "", fmt.Errorf("gemini: falha ao decodificar resposta: %w", err)
	}
	if len(res.Candidates) == 0 || len(res.Candidates[0].Content.Parts) == 0 {
		return "", fmt.Errorf("gemini: resposta sem candidatos válidos")
	}
	return res.Candidates[0].Content.Parts[0].Text, nil
}
