# Synapse CLI
## Introdução
A Synapse é uma ferramenta de linha de comando (CLI) para gerenciar commits no Git, construída com a biblioteca padrão do Go, focando em simplicidade, zero dependências externas e economia de tokens para garantir mensagens de commit rápidas e contextualmente precisas.

### Arquitetura e Filosofia
A ferramenta atua como uma ponte otimizada entre o repositório local e as APIs de LLMs (Groq e Gemini). O código é organizado em pacotes pequenos e especializados, cada um com uma única responsabilidade, mantendo o binário único e sem dependências externas.

#### Estrutura de Pacotes
* `internal/config` — carregamento e persistência de configuração (.env, idioma, chaves de API).
* `internal/ui` — interface de terminal com indicadores textuais (`[OK]`, `[ERRO]`, `[AVISO]`, `[FATAL]`) e paleta de cores sóbria.
* `internal/git` — extração do `git diff` (com exclusão de lock files e .env) e manutenção do .gitignore.
* `internal/sanitizer` — sanitização de dados sensíveis no diff (senhas, chaves de API, tokens, bearer/JWT e chaves SSH) antes de qualquer requisição HTTP.
* `internal/llm` — interface `Provider` (padrão Strategy) com implementações Groq e Gemini, clientes HTTP nativos e fallback automático.
* `internal/prompt` — construção do prompt enviado ao modelo (padrão Builder), incluindo a trava de formatação por idioma.
* `internal/commit` — execução do `git commit`.

#### Decisões Arquiteturais Chave
* **Zero Dependências:** Compilada em um único binário estático. HTTP, interações com o sistema operacional e sanitizações via regex são tratados nativamente pelo Go.
* **Economia de Tokens:** O `git diff` ignora arquivos de bloqueio (`package-lock.json`, `composer.lock`, `go.sum`, etc.) e metadados internos do Git, mantendo a janela de contexto da LLM focada apenas em alterações reais de código.
* **Segurança e Sanitização:** Expressões regulares nativas redigem credenciais (senhas, chaves de API, tokens, access/refresh tokens, client secrets, cabeçalhos `Authorization`/`Bearer`, JWTs e chaves privadas SSH/PEM) antes de qualquer solicitação HTTP.
* **Resiliência:** Fallback automático e silencioso: Groq primeiro e Gemini em seguida, caso o provedor primário falhe ou esteja sobrecarregado (HTTP 503).
* **Variedade controlada:** A cada novo "Recriar" a temperatura do modelo sobe gradualmente (base +0.2 por tentativa, teto em 0.9), gerando sugestões mais diversas sem perder coesão. A temperatura é reiniciada a cada novo ciclo de commit.

## Instalação
A Synapse compila diretamente para código de máquina, tornando a instalação direta em qualquer ambiente Linux (incluindo Manjaro e WSL).

### Compilando o Binário
Clone o repositório e compile o binário:
```bash
git clone https://github.com/Elliton-Luis/synapse.git
cd synapse
go build -o syn .
sudo mv syn /usr/local/bin/
```

## Uso
Após preparar as alterações de código, execute a ferramenta CLI em qualquer lugar do repositório:
```bash
git add .
syn
```
Na primeira execução, a Synapse solicitará as chaves de API e gerará automaticamente a configuração de ambiente (.env) e os arquivos de instrução de prompt estrito (commit_pattern.md), garantindo que sejam adicionados com segurança ao .gitignore local.

### Fluxo Interativo
Durante o fluxo, a ferramenta apresenta uma sugestão de commit e aguarda sua decisão:
```text
Sugestão de commit: feat(auth): adicione middleware de validação JWT

[Y] Confirmar   [R] Recriar   [N] Cancelar
>
```
* **Y** — confirma a sugestão e executa o commit.
* **R** — gera uma nova sugestão. A temperatura do modelo aumenta a cada tentativa (0.3 → 0.5 → 0.7 → … até 0.9) para produzir alternativas mais variadas.
* **N** — cancela a operação.

### Comandos e Flags
#### Configuração de Idioma
Alterna o idioma padrão para os prompts do sistema e as mensagens de commit geradas. Essa configuração persiste no arquivo .env.
```bash
syn lang pt
syn lang en
```
#### Sobrescrita de Provedor
Ignora o roteamento automático e força o uso de um provedor de API específico para a execução atual. Valores aceitos: `auto`, `groq`, `gemini`.
```bash
syn --provider groq
syn --provider gemini
```
#### Modelo Personalizado
Sobrescreve o modelo padrão de cada provedor para a execução atual.
```bash
syn --model llama-3.3-70b-versatile
```
#### Arquivo de Padrão Personalizado
Usa um arquivo de instrução de commit alternativo em vez do `commit_pattern.md` gerado automaticamente.
```bash
syn --pattern meu_padrao.md
```
#### Modo de Depuração
Exibe logs detalhados sobre o roteamento interno, status de fallback, arquivos carregados e a temperatura utilizada em cada geração.
```bash
syn --debug
```

### Interface de Terminal
A interface segue o estilo de ferramentas profissionais como git, docker e kubectl: indicadores textuais e paleta de cores sóbria, sem emojis.
* `[OK]` — operação concluída com sucesso.
* `[ERRO]` / `[FATAL]` — falha. `[FATAL]` encerra a execução com código de saída 1.
* `[AVISO]` — entrada inválida ou condição não fatal.
* `[DEBUG]` — logs detalhados, visíveis apenas com `--debug`.

## Roadmap de Desenvolvimento
- [x] Camada 1 — Protótipo de interface de terminal e loop de interação.
- [x] Camada 2 — Sistema de configuração isolado e configuração de ambiente.
- [x] Camada 3 — Integração RESTful nativa (Gemini + Groq) sem SDKs externos.
- [x] Camada 4 — Otimização de tokens de diferença do Git avançada e sanitização de segurança de regex.
- [x] Camada 5 — Loop de execução principal (Geração, Aprovação, Recreação e execução de commit).
- [x] Camada 6 — Polimento arquitetônico (Flags de CLI, lógica de fallback 503 e subcomandos de idioma).
- [x] Camada 7 — Refatoração arquitetural em pacotes especializados, sanitização expandida, temperatura progressiva e interface de terminal profissional.

## Contribuindo
Contribuições que visam melhorar a lógica de extração de diferença, padrões de sanitização de segurança ou desempenho geral são bem-vindas.

### Passos para Contribuir
1. Faça um fork do repositório.
2. Crie uma branch de recurso (git checkout -b feature/NovaFuncionalidade).
3. Faça commit das alterações (usando syn).
4. Faça push para a branch (git push origin feature/NovaFuncionalidade).
5. Abra uma solicitação de pull request.

---

# Synapse CLI
## Introduction
Synapse is a command-line interface (CLI) tool for managing Git commits, built with the Go standard library, focusing on simplicity, zero external dependencies, and token economy to ensure fast and contextually accurate commit messages.

### Architecture and Philosophy
The tool acts as a highly optimized bridge between the local repository and LLM APIs (Groq and Gemini). The codebase is organized into small, specialized packages, each with a single responsibility, while keeping a single binary with no external dependencies.

#### Package Structure
* `internal/config` — loads and persists configuration (.env, language, API keys).
* `internal/ui` — terminal interface with text indicators (`[OK]`, `[ERRO]`, `[AVISO]`, `[FATAL]`) and a sober color palette.
* `internal/git` — `git diff` extraction (excluding lock files and .env) and .gitignore maintenance.
* `internal/sanitizer` — redaction of sensitive data in the diff (passwords, API keys, tokens, bearer/JWT and SSH keys) before any HTTP request.
* `internal/llm` — `Provider` interface (Strategy pattern) with Groq and Gemini implementations, native HTTP clients and automatic fallback.
* `internal/prompt` — builds the prompt sent to the model (Builder pattern), including the per-language formatting safety lock.
* `internal/commit` — executes `git commit`.

#### Key Architectural Decisions
* **Zero Dependencies:** Compiled into a single static binary. HTTP, OS interactions and regex sanitization are all handled natively by Go.
* **Token Economy:** The `git diff` ignores lock files (`package-lock.json`, `composer.lock`, `go.sum`, etc.) and internal Git metadata, keeping the LLM context window focused on actual code changes.
* **AppSec & Sanitization:** Native regular expressions redact credentials (passwords, API keys, tokens, access/refresh tokens, client secrets, `Authorization`/`Bearer` headers, JWTs and SSH/PEM private keys) before any HTTP request.
* **Resiliency:** Automatic, silent fallback: Groq first, then Gemini, if the primary provider fails or is overloaded (HTTP 503).
* **Controlled variety:** On every "Recriar" (Regenerate), the model temperature rises gradually (base +0.2 per attempt, capped at 0.9), producing more diverse suggestions without losing coherence. The temperature resets on each new commit cycle.

## Installation
Synapse compiles directly to machine code, making installation straightforward on any Linux environment (including Manjaro and WSL).

### Compiling the Binary
Clone the repository and compile the binary:
```bash
git clone https://github.com/Elliton-Luis/synapse.git
cd synapse
go build -o syn .
sudo mv syn /usr/local/bin/
```

## Usage
After staging your code changes, execute the CLI tool from anywhere in your repository:
```bash
git add .
syn
```
On the first execution, Synapse will prompt you for your API keys and automatically generate its environment configuration (.env) and strict prompt instruction files (commit_pattern.md), ensuring they are safely added to your local .gitignore.

### Interactive Flow
During the flow, the tool presents a commit suggestion and waits for your decision:
```text
Sugestão de commit: feat(auth): adicione middleware de validação JWT

[Y] Confirmar   [R] Recriar   [N] Cancelar
>
```
* **Y** — accepts the suggestion and runs the commit.
* **R** — generates a new suggestion. The model temperature rises on each attempt (0.3 → 0.5 → 0.7 → … up to 0.9) to produce more varied alternatives.
* **N** — cancels the operation.

### Commands & Flags
#### Language Configuration
Toggles the default language for the system prompts and the generated commit messages. This setting persists in the .env file.
```bash
syn lang pt
syn lang en
```
#### Provider Override
Bypasses the automatic routing and forces the use of a specific API provider for the current execution. Accepted values: `auto`, `groq`, `gemini`.
```bash
syn --provider groq
syn --provider gemini
```
#### Custom Model
Overrides the default model of each provider for the current execution.
```bash
syn --model llama-3.3-70b-versatile
```
#### Custom Pattern File
Uses an alternative commit instruction file instead of the auto-generated `commit_pattern.md`.
```bash
syn --pattern my_pattern.md
```
#### Debug Mode
Outputs detailed logs regarding the internal routing, fallback status, loaded files, and the temperature used on each generation.
```bash
syn --debug
```

### Terminal Interface
The interface follows the style of professional tools such as git, docker, and kubectl: text indicators and a sober color palette, with no emojis.
* `[OK]` — operation completed successfully.
* `[ERRO]` / `[FATAL]` — failure. `[FATAL]` terminates execution with exit code 1.
* `[AVISO]` — invalid input or non-fatal condition.
* `[DEBUG]` — detailed logs, visible only with `--debug`.

## Development Roadmap
- [x] Layer 1 — Terminal interface prototype and interaction loop.
- [x] Layer 2 — Isolated configuration system and environment setup.
- [x] Layer 3 — Native RESTful integration (Gemini + Groq) without external SDKs.
- [x] Layer 4 — Advanced Git diff token optimization and Regex security sanitization.
- [x] Layer 5 — Main execution loop (Generation, Approval, Recreation, and Commit execution).
- [x] Layer 6 — Architectural polish (CLI Flags, 503 Fallback logic, and Language subcommands).
- [x] Layer 7 — Architectural refactor into specialized packages, expanded sanitization, progressive temperature, and a professional terminal interface.

## Contributing
Contributions focusing on improving the diff extraction logic, security sanitization patterns, or overall performance are welcome.

### Steps to Contribute
1. Fork the repository.
2. Create a feature branch (git checkout -b feature/NewFeature).
3. Commit your changes (using syn).
4. Push to the branch (git push origin feature/NewFeature).
5. Open a Pull Request.
