import os

def create_file(path, content):
    # Pega o nome do diretório
    directory = os.path.dirname(path)
    
    # Só tenta criar se o caminho realmente tiver um diretório (ex: 'prompts/')
    if directory:
        os.makedirs(directory, exist_ok=True)
        
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip())
        print(f"✅ Criado: {path}")
    else:
        print(f"⏩ Já existe: {path}")
        
# --- CONTEÚDOS DOS ARQUIVOS ---
env_content = """
# Draftly - API Keys
GROQ_API_KEY=sua_chave_aqui
DEEPSEEK_API_KEY=sua_chave_aqui
GEMINI_API_KEY=sua_chave_aqui
"""

# O prompt que define o comportamento agressivo de MVP
architect_prompt = """
Você é um Arquiteto de Software Sênior e Especialista em Produtos (The Carver).
Sua missão é extrair o MVP de qualquer ideia, sendo impiedoso com o overengineering.

DIRETRIZES:
1. FOCO NO CAMINHO DE OURO: Identifique a única funcionalidade que faz o projeto valer a pena.
2. REGRA DO 3: Sugira no máximo 3 tabelas no banco e 3 funções core para o v1.
3. ANTI-ESCOPO: Liste explicitamente o que NÃO deve ser feito agora (ex: auth complexo, dashboards, microserviços).
4. LINGUAGEM: Seja técnico, fale de trade-offs, jargões de engenharia e versões estáveis (Laravel 11, Python 3.12+, etc).
"""

# O template do documento final
blueprint_tpl = """
# Blueprint: [NOME_DO_PROJETO]

## 1. CORE MISSION (O Caminho de Ouro)
> [Resumo da funcionalidade principal]

## 2. O ESQUELETO (Data Model)
- **Entidades:** [Tabela A], [Tabela B], [Tabela C]
- **Relacionamentos:** [Como elas se conectam]

## 3. TECH STACK (Apenas o necessário)
- **Linguagem/Framework:** [Stack]
- **Infra/DB:** [Ex: SQLite/Docker]

## 4. ANTI-ESCOPO (Proibido no v1)
- [O que você NÃO vai codar agora para não perder o foco]

## 5. CHECKLIST DIA 1 (Mão na massa)
- [ ] [Tarefa 1]
- [ ] [Tarefa 2]
"""

def setup():
    print("--- DRAFTLY: INICIANDO SETUP ---")
    create_file(".env", env_content)
    create_file("prompts/architect.md", architect_prompt)
    create_file("templates/blueprint.md", blueprint_tpl)
    print("\n[!] Setup pronto. Edite o .env e depois use: uv run main.py")

if __name__ == "__main__":
    setup()