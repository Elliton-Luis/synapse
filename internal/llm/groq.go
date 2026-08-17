package llm

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

const groqURL = "https://api.groq.com/openai/v1/chat/completions"

type groqMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type groqPayload struct {
	Model       string        `json:"model"`
	Messages    []groqMessage `json:"messages"`
	Temperature float64       `json:"temperature"`
}

// Groq is a Provider implementation backed by the Groq API.
type Groq struct {
	apiKey string
	model  string
}

// NewGroq creates a Groq provider. The model may be empty, in which case
// DefaultGroqModel is used by the caller.
func NewGroq(apiKey, model string) *Groq {
	return &Groq{apiKey: apiKey, model: model}
}

func (g *Groq) Name() string { return ProviderGroq }

// BaseTemperature returns the default Groq generation temperature.
func (g *Groq) BaseTemperature() float64 { return DefaultGroqTemperature }

func (g *Groq) GenerateCommit(prompt string, temperature float64) (string, error) {
	bodyData := groqPayload{
		Model: g.model,
		Messages: []groqMessage{
			{Role: "system", Content: "You are a strict Git commit message generator. Return ONLY the final commit message. No quotes, no markdown, no explanations."},
			{Role: "user", Content: prompt},
		},
		Temperature: temperature,
	}

	jsonData, err := json.Marshal(bodyData)
	if err != nil {
		return "", fmt.Errorf("groq: falha ao serializar payload: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, groqURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return "", fmt.Errorf("groq: falha ao criar request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+g.apiKey)
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 10 * time.Second}
	respBody, err := sendRequest(client, req)
	if err != nil {
		return "", err
	}

	var res struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(respBody, &res); err != nil {
		return "", fmt.Errorf("groq: falha ao decodificar resposta: %w", err)
	}
	if len(res.Choices) == 0 {
		return "", fmt.Errorf("groq: resposta vazia retornada pela API")
	}
	return res.Choices[0].Message.Content, nil
}
