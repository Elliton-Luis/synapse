# Plano de Melhorias — Synapse CLI

> Documento técnico com análise completa e priorização de melhorias para tornar o projeto robusto, profissional e pronto para produção em escala industrial.

---

## 1. Arquitetura e Organização

### Pontos Fortes
- Separação clara em `internal/config`, `internal/ui` e `main.go` (entry point)
- Conceito de "zero dependências" bem executado — apenas stdlib
- Arquitetura de *fallback* automático (Groq → Gemini em 503)
- Estrutura simples e direta para um CLI pequeno

### Pontos Fracos
- **Tudo em `main.go` (508 linhas)** — violação de responsabilidade única; lógica de diff, sanitização, HTTP clients, prompt building, loop de UI tudo misturado
- Ausência de camada de domínio/serviços (ex: `internal/llm`, `internal/git`, `internal/sanitizer`)
- Configuração hardcoded em constantes no topo do `main.go`
- `internal/ui` muito acoplado a `fmt`/`os` — difícil de testar
- Padrão de projeto: nenhum explícito (poderia usar *Strategy* para providers, *Builder* para prompt)

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Extrair `GitDiffService`, `Sanitizer`, `LLMClient` (interface + impls Groq/Gemini), `PromptBuilder`, `CommitExecutor` para pacotes próprios | **Alto** | Médio |
| Introduzir interface `Provider` com `GenerateCommit(prompt string) (string, error)` | **Alto** | Baixo |
| Mover constantes para `internal/config/constants.go` ou struct de config | **Médio** | Baixo |
| Inverter dependência de UI — passar `io.Reader`/`io.Writer` para permitir testes | **Médio** | Baixo |

---

## 2. Qualidade do Código

### Pontos Fortes
- Código legível, nomes claros (`sanitizeDiff`, `getGitDiff`, `callGroqAPI`)
- Uso correto de `defer` para `resp.Body.Close()`
- Sanitização de diff com regex bem pensada (remove index, mode, credenciais)
- Truncamento de diff (2000 linhas) e commit (200 chars) — proteção contra token overflow

### Pontos Fracos
- **Ignorar erros de `json.Marshal`** (linhas 400, 472): `jsonData, _ := json.Marshal(...)` — se falhar, envia body vazio
- **`exec.Command` sem validação de injection** — embora args sejam fixos, `git diff` recebe paths hardcoded; ok hoje, mas frágil
- Duplicação de lógica entre `callGroqAPI` e `callGeminiAPI` (HTTP client, error handling, JSON parsing)
- `loadPattern` retorna padrão hardcoded silenciosamente se arquivo não existe — mascaram erro de config
- `ensureGitignore` falha silenciosamente (linha 293: `return` sem erro)
- `debugMode` global — não thread-safe (irrelevante para CLI single-thread, mas mau hábito)
- Magic strings espalhadas (`"groq"`, `"gemini"`, `"auto"`, `"en"`, `"pt"`)

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Tratar erro de `json.Marshal` — retornar erro explícito | **Alto** | Baixo |
| Criar `HTTPClient` compartilhado com timeout configurável | **Médio** | Baixo |
| Substituir magic strings por `enum`/constantes tipadas | **Médio** | Baixo |
| Retornar erro em `loadPattern` se arquivo obrigatório não existe | **Médio** | Baixo |
| `ensureGitignore` retornar erro ou logar falha | **Baixo** | Baixo |

---

## 3. Boas Práticas

### Pontos Fortes
- `.env` com permissão `0600` (apenas owner read/write)
- Variáveis de ambiente têm prioridade sobre `.env`
- Timeout em HTTP clients (10s/12s)
- `defer resp.Body.Close()` presente
- Sanitização de credenciais **antes** de enviar para LLM

### Pontos Fracos
- **Nenhum teste** — zero testes unitários, de integração ou e2e
- **Nenhum logging estruturado** — apenas `fmt.Printf` com ANSI codes
- Validação de entrada mínima: `--provider` aceita qualquer string, `--model` não validado
- `flag.Parse()` chamado **após** interceptação manual de `lang` — flag parsing não padrão
- Sem `go vet`, `golangci-lint`, `staticcheck` no CI
- Tratamento de erro inconsistente: às vezes `ui.Fatal`, às vezes `os.Exit(1)`, às vezes retorna erro

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Adicionar testes unitários para `sanitizeDiff`, `config.Load`, `PromptBuilder` | **Alto** | Médio |
| Adicionar `golangci-lint` + `go vet` no CI | **Alto** | Baixo |
| Usar `slog` (stdlib) para logging estruturado com níveis | **Médio** | Baixo |
| Validar flags `--provider` e `--model` com lista permitida | **Médio** | Baixo |
| Padronizar error handling: retornar `error` e tratar no `main` | **Médio** | Baixo |

---

## 4. Segurança

### Pontos Fortes
- Sanitização de secrets no diff (regex para password, token, api_key, secret)
- `.env` com `0600` e auto-adicionado ao `.gitignore`
- Exclusão de arquivos sensíveis no `git diff` (`.env*`, lock files)
- Nenhuma dependência externa = superfície de ataque mínima

### Pontos Fracos
- **Regex de sanitização incompleta** — não cobre: `private_key`, `access_token`, `refresh_token`, `bearer`, `authorization`, `secret_key`, `client_secret`, chaves SSH (`BEGIN.*PRIVATE KEY`), JWTs
- **Sem rate limiting / retry com backoff** — pode estourar quota da API
- **API keys em memória plaintext** — ok para CLI, mas sem zeroization
- `--debug` pode vazar prompt/diff em logs (embora só mostre routing)
- `git diff` executa com `--cached` mas sem validar se está em repo git (erro genérico)

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Expandir regex de sanitização (private keys, JWTs, bearer tokens, auth headers) | **Alto** | Baixo |
| Adicionar retry com exponential backoff (respeitar `Retry-After`) | **Médio** | Médio |
| Validar se está em repo git antes de `git diff` (verificar `.git`) | **Baixo** | Baixo |
| Ofuscar API keys em memória após uso (opcional, Go GC não garante) | **Baixo** | Médio |

---

## 5. Escalabilidade e Performance

### Pontos Fortes
- Binário único, startup instantâneo
- Diff truncado em 2000 linhas — protege contexto LLM
- Timeout curto em HTTP (10-12s)
- Zero dependências = build rápido, deploy trivial

### Pontos Fracos
- **Uma requisição por vez** — sem paralelismo (irrelevante para CLI interativo)
- **Sem cache** — mesmo diff gera nova request se usuário der "Recriar"
- `git diff` roda a cada iteração do loop (linha 109 fora do loop, ok)
- Groq e Gemini chamados sequencialmente no fallback — latência soma
- `maxDiffLines` e `maxCommitLength` hardcoded

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Cache de sugestão por hash do diff (evita re-request no "Recriar") | **Médio** | Médio |
| Tornar `maxDiffLines` e `maxCommitLength` configuráveis via flag/env | **Baixo** | Baixo |
| Paralelizar chamadas Groq+Gemini no modo "auto" (race com context) | **Baixo** | Médio |

---

## 6. Testes

### Estado Atual
**ZERO testes.** Nenhum arquivo `*_test.go` no projeto.

### Lacunas Críticas
- `sanitizeDiff` — lógica complexa de regex, **precisa de testes** (cases: credenciais, index lines, mode lines, empty lines, edge cases)
- `config.Load` / `setup` / `readEnv` / `SetLang` — fluxos de arquivo, env vars, permissões
- `PromptBuilder` (extrair de main) — composição de prompt, safety lock por idioma
- `LLMClient` mocks — testar fallback, error handling, parsing de resposta
- Integração: `git diff` parsing, commit execution

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Criar `sanitize_diff_test.go` com tabela de casos (mínimo 10 cases) | **Alto** | Baixo |
| Testes para `config` package (Load, SetLang, prioridade env vs file) | **Alto** | Baixo |
| Introduzir `testify/mock` ou mocks manuais para `Provider` interface | **Médio** | Médio |
| Teste de integração e2E com `git init` temporário (opcional) | **Médio** | Alto |

---

## 7. Documentação

### Pontos Fortes
- **README excelente** — bilingue (PT/EN), arquitetura explicada, installation, usage, flags, roadmap
- `commit_pattern.md` e `commit_pattern_pt.md` versionados como templates
- Comentários no código explicam seções principais (`// ==========================================`)

### Pontos Fracos
- **Nenhum docstring** em funções públicas (`Load`, `SetLang`, `callGroqAPI`, etc.)
- Sem `go doc` útil — funções não exportadas (tudo lowercase) ou sem comentários
- Sem `CHANGELOG.md`
- Sem documentação de arquitetura (ADR) para decisões como "zero deps", "fallback 503"
- `.env` example não existe (`.env.example`)

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| Adicionar docstrings em todas as funções exportadas (pacotes `config`, `ui`) | **Médio** | Baixo |
| Criar `.env.example` com placeholders | **Baixo** | Trivial |
| Adicionar `CHANGELOG.md` | **Baixo** | Baixo |
| Documentar regex de sanitização no README (transparência) | **Baixo** | Baixo |

---

## 8. DevOps / CI-CD

### Estado Atual
**Nenhum.** Não há:
- GitHub Actions / GitLab CI
- Dockerfile
- Makefile / Taskfile
- Scripts de release (goreleaser)
- Verificação de vulnerabilidades (`govulncheck`)

### Sugestões (Prioridade)

| Melhoria | Impacto | Esforço |
|----------|---------|---------|
| GitHub Actions: `go build`, `go vet`, `golangci-lint`, `go test`, `govulncheck` | **Alto** | Baixo |
| `goreleaser` para releases multi-platform (Linux, macOS, Windows, ARM) | **Médio** | Baixo |
| `Makefile` ou `Taskfile.yml` para comandos comuns (build, test, lint, install) | **Médio** | Baixo |
| Dockerfile (multi-stage, distroless/scratch) | **Baixo** | Baixo |
| `dependabot.yml` para updates de Go version | **Baixo** | Trivial |

---

## Resumo Executivo — Top 5 Melhorias Críticas

| # | Melhoria | Categoria | Justificativa |
|---|----------|-----------|---------------|
| **1** | **Adicionar testes unitários** (`sanitizeDiff`, `config`, `PromptBuilder`) | Testes / Qualidade | Código sem testes é inconfiável em produção; sanitização de secrets **precisa** de cobertura |
| **2** | **Extrair camadas de domínio** (`Provider` interface, `GitService`, `Sanitizer`, `PromptBuilder`) | Arquitetura | `main.go` com 508 linhas viola SRP; impede testes, manutenção, extensão (ex: novo provider) |
| **3** | **Expandir regex de sanitização** (private keys, JWTs, bearer, auth headers) | Segurança | Atual regex deixa vazar chaves SSH, JWTs, tokens OAuth — risco real de exposição |
| **4** | **CI/CD com lint + vet + vuln check + tests** | DevOps / Qualidade | Sem automação, regressões entram silenciosamente; `golangci-lint` pega bugs comuns |
| **5** | **Tratar erros de `json.Marshal` + padronizar error handling** | Qualidade / Robustez | Ignorar erro de marshalling envia request inválido; error handling inconsistente dificulta debug |

---

## Próximos Passos Recomendados (Ordem de Execução)

1. **Criar estrutura de pacotes**: `internal/llm`, `internal/git`, `internal/sanitizer`, `internal/prompt`
2. **Escrever testes para `sanitizeDiff`** (maior risco de segurança)
3. **Implementar interface `Provider`** e mover Groq/Gemini para impls separados
4. **Configurar GitHub Actions** com `golangci-lint`, `go vet`, `go test`, `govulncheck`
5. **Expandir sanitização** com casos de teste adicionais
6. **Adicionar `goreleaser`** para distribuição
7. **Documentar APIs públicas** com docstrings

---

## Referências de Código

- `main.go:400,472` — `json.Marshal` sem tratamento de erro
- `main.go:309-322` — `sanitizeDiff` (regex de sanitização)
- `main.go:378-507` — `callGroqAPI` / `callGeminiAPI` (duplicação)
- `internal/config/config.go` — Config loading, sem testes
- `internal/ui/ui.go` — UI acoplada a `os.Stdin`/`os.Stdout`