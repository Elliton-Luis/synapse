package llm

import "testing"

func TestTemperatureFor(t *testing.T) {
	cases := []struct {
		name       string
		base       float64
		retryCount int
		want       float64
	}{
		{"first attempt gemini", DefaultGeminiTemperature, 0, 0.3},
		{"first retry gemini", DefaultGeminiTemperature, 1, 0.5},
		{"second retry gemini", DefaultGeminiTemperature, 2, 0.7},
		{"third retry gemini", DefaultGeminiTemperature, 3, 0.9},
		{"capped at max", DefaultGeminiTemperature, 10, 0.9},
		{"first attempt groq", DefaultGroqTemperature, 0, 0.5},
		{"first retry groq", DefaultGroqTemperature, 1, 0.7},
		{"groq reaches cap", DefaultGroqTemperature, 2, 0.9},
	}
	for _, c := range cases {
		if got := TemperatureFor(c.base, c.retryCount); got != c.want {
			t.Errorf("%s: TemperatureFor(%v, %d) = %v, want %v", c.name, c.base, c.retryCount, got, c.want)
		}
	}
}
