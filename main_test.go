package main

import (
	"fmt"
	"strings"
	"testing"

	"github.com/Elliton-Luis/synapse/internal/llm"
)

type fakeProvider struct {
	name      string
	temps     []float64
	base      float64
	failFirst bool
}

func (f *fakeProvider) Name() string { return f.name }
func (f *fakeProvider) BaseTemperature() float64 {
	return f.base
}
func (f *fakeProvider) GenerateCommit(prompt string, temperature float64) (string, error) {
	f.temps = append(f.temps, temperature)
	return fmt.Sprintf("sugestao %d", len(f.temps)), nil
}

func TestGenerateEscalatesTemperature(t *testing.T) {
	p := &fakeProvider{name: "groq", base: 0.5}
	providers := []llm.Provider{p}

	for retry := 0; retry < 3; retry++ {
		s, err := generate(providers, "prompt", retry)
		if err != nil {
			t.Fatalf("generate retry %d: %v", retry, err)
		}
		if !strings.HasPrefix(s, "sugestao") {
			t.Fatalf("unexpected suggestion %q", s)
		}
	}
	want := []float64{0.5, 0.7, 0.9}
	for i := range want {
		if p.temps[i] != want[i] {
			t.Errorf("attempt %d temperature = %.2f, want %.2f", i+1, p.temps[i], want[i])
		}
	}
}
