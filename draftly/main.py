# /// script
# dependencies = [
#   "google-genai",
#   "openai",
# ]
# ///

import os
import time
from google import genai
from openai import OpenAI

# --- AUXILIARES DE AMBIENTE ---
def load_env():
    """Carrega o .env manualmente para manter o script leve."""
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value.strip()

def get_file(path, default=""):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return default

# Carregamento Inicial
load_env()
SYSTEM_PROMPT = get_file("prompts/architect.md", "Você é um arquiteto de software.")
BLUEPRINT_TPL = get_file("templates/blueprint.md", "# Projeto [NOME]")

# --- INTEGRAÇÃO COM IAs ---
def call_ai_service(provider, prompt):
    api_key = os.getenv(f"{provider}_API_KEY")
    if not api_key or "sua_chave" in api_key:
        return None, f"Chave {provider} ausente."

    start = time.time()
    try:
        if provider == "GROQ":
            client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": prompt}]
            )
            return res.choices[0].message.content, f"GROQ | {time.time()-start:.2f}s"
        
        elif provider == "DEEPSEEK":
            client = OpenAI(base_url="https://api.deepseek.com", api_key=api_key)
            res = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": prompt}]
            )
            return res.choices[0].message.content, f"DEEPSEEK | {time.time()-start:.2f}s"

        elif provider == "GEMINI":
            client = genai.Client(api_key=api_key)
            full_prompt = f"{SYSTEM_PROMPT}\n\nREQUISIÇÃO:\n{prompt}"
            res = client.models.generate_content(model="gemini-2.0-flash", contents=full_prompt)
            return res.text, f"GEMINI | {time.time()-start:.2f}s"
            
    except Exception as e:
        return None, f"{provider}_ERR: {str(e)}"

def ask_ai(prompt):
    """Fallback dinâmico entre provedores."""
    for p in ["GROQ", "DEEPSEEK", "GEMINI"]:
        res, stats = call_ai_service(p, prompt)
        if res:
            print(f"      [LOG] {stats}")
            return res
    return None

# --- WORKFLOW CLI ---
def main():
    os.system('clear' if os.name == 'posix' else 'cls')
    print("="*60)
    print(" DRAFTLY v2.1 - SOFTWARE ARCHITECT (UV MODE)")
    print("="*60)
    
    idea = input("[?] Qual a ideia do projeto? ").strip()
    p_name = input("[?] Nome do projeto: ").strip()
    
    print("\n[!] Escolha a Intensidade:")
    print("    1. MVP 'The Carver' (Foco em entrega rápida e corte de gordura)")
    print("    2. Produto Completo (Escalabilidade e Infra)")
    is_mvp = input("[?] Opção: ") == "1"

    # FASE 1: PERGUNTAS DE ESTRUTURA
    print(f"\n[PHASE] Analisando contexto...")
    q_prompt = f"Ideia: '{idea}'. Gere 3 perguntas de múltipla escolha para definir a stack e o core técnico. Foco em {'MVP' if is_mvp else 'Produto'}. Formato: [TEMA] Pergunta?"
    
    qs_raw = ask_ai(q_prompt)
    if not qs_raw: return

    answers = []
    for line in [l for l in qs_raw.split('\n') if '?' in l]:
        print(f"\nARCHITECT: {line.strip()}")
        ans = input("YOU (ou 'ns' para conselho): ").strip()
        
        if ans.lower() in ["ns", "nao sei", "ajuda"]:
            print(f"\n--- CONSELHO: ---\n{ask_ai(f'Dê um conselho rápido sobre {line} para o projeto {idea}')}\n---")
            ans = input("SUA DECISÃO: ")
        answers.append(f"Q: {line} | A: {ans}")

    # FASE 2: GERAÇÃO DO BLUEPRINT FINAL
    print("\n[PHASE] Gerando Blueprint...")
    final_prompt = f"""
    Gere o Blueprint final para '{p_name}'.
    Decisões tomadas: {answers}
    Use o template abaixo e seja agressivo no ANTI-ESCOPO se for MVP:
    {BLUEPRINT_TPL}
    """
    
    doc = ask_ai(final_prompt)
    if doc:
        fname = f"blueprint_{p_name.lower().replace(' ', '_')}.md"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"\n[SUCESSO] Arquivo gerado: {fname}")

if __name__ == "__main__":
    main()