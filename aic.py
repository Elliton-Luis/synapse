#!/usr/bin/env python3
import os
import subprocess
import requests
import sys
import argparse
import logging
import re
from typing import Optional

from google import genai

# ==========================================
# CONFIGURAÇÕES GERAIS
# ==========================================
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
# Aumentado de 500 para 2000 para dar muito mais contexto à IA
MAX_DIFF_LINES = 2000
MAX_COMMIT_LENGTH = 200

# ==========================================
# FUNÇÕES DE UTILIDADE E GIT
# ==========================================
def ensure_gitignore():
    """Verifica e adiciona os arquivos de padrão ao .gitignore automaticamente."""
    if not os.path.exists(".git"):
        return

    patterns_to_ignore = ["commit_pattern.md", "commit_pattern_pt.md"]
    gitignore_path = ".gitignore"
    
    content = ""
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

    missing = [p for p in patterns_to_ignore if p not in content]
    
    if missing:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write("\n# Ignorado automaticamente pelo CLI AI Commit\n")
            for m in missing:
                f.write(f"{m}\n")
        logging.info("Padrões de commit adicionados ao .gitignore automaticamente.")

def sanitize_diff(diff_text: str) -> str:
    """Varre o diff e oculta valores de chaves sensíveis."""
    regex = re.compile(r'(?i)(password|token|api_key|secret)(\s*[:=>]\s*)([\'"].*?[\'"]|[^\s\n\r,;]+)')
    return regex.sub(r'\1\2[REDACTED]', diff_text)

def get_git_diff() -> Optional[str]:
    try:
        cmd = [
            "git", "diff", "--cached", 
            "--", ".", 
            ":(exclude).env", 
            ":(exclude)*.env.*"
        ]
        diff = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8")
        
        if not diff.strip():
            logging.warning("Nenhuma alteração no stage (arquivos .env são ignorados). Use 'git add' primeiro.")
            return None
            
        return sanitize_diff(diff)
        
    except subprocess.CalledProcessError as e:
        logging.error("Falha ao executar o Git. Verifique se este é um repositório válido.")
        logging.debug(f"Detalhes: {e.output.decode('utf-8')}")
        return None
    except FileNotFoundError:
        logging.error("Comando 'git' não encontrado no sistema.")
        return None

# ==========================================
# CLIENTES DE API
# ==========================================
class GroqClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def generate_commit(self, prompt: str) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Você é um gerador estrito de mensagens de commit Git. Retorne APENAS a mensagem final. Sem aspas, sem markdown extra."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5
        }

        try:
            logging.debug(f"Enviando requisição para Groq (Modelo: {self.model})...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if not isinstance(data, dict) or 'choices' not in data or not data['choices']:
                return None
            return data['choices'][0].get('message', {}).get('content', '').strip()
        except Exception as e:
            logging.error(f"Erro no Groq: {e}")
            return None


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def generate_commit(self, prompt: str) -> Optional[str]:
        try:
            logging.debug(f"Enviando para Gemini ({self.model}) via SDK...")
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": 0.3,
                    # Aumentado de 200 para 500 para dar mais margem
                    "max_output_tokens": 500,
                    "system_instruction": "Você é um gerador estrito de mensagens de commit Git. Retorne APENAS a mensagem final, sem aspas ou explicações."
                }
            )

            if not response or not response.text:
                logging.error("O Gemini retornou uma resposta vazia.")
                return None
                
            return response.text.strip()

        except Exception as e:
            logging.error(f"Erro no SDK do Gemini: {e}")
            return None

# ==========================================
# ORQUESTRADOR PRINCIPAL
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Gerador de Commits via IA")
    parser.add_argument("--provider", choices=["groq", "gemini", "auto"], default="gemini", help="Força um provedor (default: gemini)")
    parser.add_argument("--model", type=str, help="Sobrescreve o modelo padrão")
    parser.add_argument("--debug", action="store_true", help="Ativa logs detalhados")
    parser.add_argument("--pattern", type=str, default="commit_pattern.md", help="Arquivo de padrão a ser lido")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(format="%(levelname)s: %(message)s", level=log_level)

    # 1. Garante que os arquivos .md não vazem pro repositório
    ensure_gitignore()

    # 2. Captura e limpa o diff
    diff = get_git_diff()
    if not diff:
        sys.exit(1)

    diff = "\n".join(diff.splitlines()[:MAX_DIFF_LINES])

    # 3. Carrega o padrão
    pattern_path = os.path.join(os.getcwd(), args.pattern)
    try:
        with open(pattern_path, "r", encoding="utf-8") as f:
            pattern = f.read()
            logging.debug(f"Padrão carregado de: {pattern_path}")
    except FileNotFoundError:
        logging.debug(f"Arquivo {args.pattern} não encontrado. Usando regras padrão.")
        pattern = "Siga o padrão Conventional Commits rigidamente. Máximo de 1 linha."

    # Salvamos o prompt base para não concatenar lixo infinitamente caso o usuário aperte "R" várias vezes
    base_prompt = f"Padrão exigido:\n{pattern}\n\nAnalise o seguinte git diff e gere UMA mensagem de commit:\n{diff}"
    
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    retry_count = 0

    while True:
        suggestion = None
        
        # Constrói o prompt dinâmico baseado na quantidade de tentativas
        current_prompt = base_prompt
        if retry_count > 0:
            current_prompt += f"\n\nO usuário rejeitou as {retry_count} sugestões anteriores. Gere uma mensagem de commit diferente das anteriores. Tente focar em outro aspecto das alterações ou use uma abordagem descritiva diferente."

        # 4. Roteamento de IA
        if args.provider in ["auto", "groq"]:
            if groq_key:
                model = args.model if args.model and args.provider == "groq" else DEFAULT_GROQ_MODEL
                client = GroqClient(groq_key, model)
                suggestion = client.generate_commit(current_prompt)
            elif args.provider == "groq":
                logging.error("GROQ_API_KEY não definida.")

        if not suggestion and args.provider in ["auto", "gemini"]:
            if args.provider == "auto" and groq_key:
                logging.debug("Realizando fallback para Gemini...")
            if not gemini_key:
                logging.error("GEMINI_API_KEY não definida no ambiente (export GEMINI_API_KEY='sua_chave').")
                sys.exit(1)
            else:
                model = args.model if args.model and args.provider == "gemini" else DEFAULT_GEMINI_MODEL
                client = GeminiClient(gemini_key, model)
                suggestion = client.generate_commit(current_prompt)

        if not suggestion:
            logging.fatal("Falha ao gerar sugestão de commit. Verifique suas chaves de API e conexão.")
            sys.exit(1)

        # 5. Formatação rigorosa da resposta
        suggestion = suggestion.replace('"', '').replace('`', '').strip()
        suggestion = suggestion.splitlines()[0]
        
        if len(suggestion) > MAX_COMMIT_LENGTH:
            suggestion = suggestion[:MAX_COMMIT_LENGTH]

        # 6. Exibição e Confirmação
        print(f"\n✨ Sugestão da IA: \033[1;32m{suggestion}\033[0m")
        
        try:
            confirm = input("\n[Y] Confirmar | [N] Cancelar | [R] Recriar: ").strip().lower()
            
            if confirm == 'y':
                subprocess.run(["git", "commit", "-m", suggestion], check=True)
                print("🚀 Commit realizado com sucesso!")
                break
            elif confirm == 'r':
                retry_count += 1
                continue
            else:
                print("Abortado pelo usuário.")
                break
        except subprocess.CalledProcessError:
            logging.error(f"Falha ao executar o git commit. O Git retornou um erro.")
            break
        except KeyboardInterrupt:
            print("\nOperação cancelada.")
            sys.exit(0)

if __name__ == "__main__":
    main()