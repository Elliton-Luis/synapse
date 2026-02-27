#!/home/chocotonilitz/scripts/venv/bin/python
import os
import subprocess
import requests
import sys
import argparse
import logging
import re
import time
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from functools import lru_cache

# ==========================================
# CONFIGURAÇÕES GERAIS
# ==========================================
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
MAX_DIFF_LINES = 300
MAX_COMMIT_LENGTH = 200
REQUEST_TIMEOUT = 6
LARGE_DIFF_THRESHOLD = 100
VERY_LARGE_DIFF_THRESHOLD = 300

# Cores para terminal
class Colors:
    INFO = '\033[0;34m'
    SUCCESS = '\033[0;32m'
    WARNING = '\033[0;33m'
    ERROR = '\033[0;31m'
    HIGHLIGHT = '\033[1;37m'
    RESET = '\033[0m'
    GRAY = '\033[0;90m'

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

def count_diff_lines(diff_text: str) -> int:
    """Conta o número de linhas relevantes no diff"""
    if not diff_text:
        return 0
    return len([l for l in diff_text.splitlines() if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))])

def parse_diff_intelligently(diff_text: str, max_lines: int = 50) -> str:
    """
    Parseia o diff de forma inteligente:
    - Para diffs pequenos: mostra tudo
    - Para diffs grandes: mostra amostra + estatísticas
    """
    if not diff_text or not diff_text.strip():
        return ""
    
    lines = diff_text.splitlines()
    file_changes: Dict[str, List[str]] = {}
    current_file = None
    total_additions = 0
    total_deletions = 0
    
    # Primeira passada: conta estatísticas
    for line in lines:
        if line.startswith('+++ b/'):
            current_file = line[6:]
            if current_file not in file_changes:
                file_changes[current_file] = []
        elif line.startswith('+') and not line.startswith('+++'):
            total_additions += 1
        elif line.startswith('-') and not line.startswith('---'):
            total_deletions += 1
    
    # Segunda passada: coleta amostra
    samples_per_file = max(1, max_lines // max(1, len(file_changes)))
    file_samples = {}
    current_file = None
    
    for line in lines:
        if line.startswith('+++ b/'):
            current_file = line[6:]
            if current_file not in file_samples:
                file_samples[current_file] = []
        elif line.startswith('+') and not line.startswith('+++') and current_file:
            if len(file_samples[current_file]) < samples_per_file:
                content = line[1:].strip()
                if content and len(content) < 80:
                    file_samples[current_file].append(f"+{content[:40]}...")
        elif line.startswith('-') and not line.startswith('---') and current_file:
            if len(file_samples[current_file]) < samples_per_file:
                content = line[1:].strip()
                if content and len(content) < 80:
                    file_samples[current_file].append(f"-{content[:40]}...")
    
    # Formata output
    output = []
    output.append(f"SUMMARY: {total_additions} additions, {total_deletions} deletions in {len(file_changes)} files")
    
    for file, samples in file_samples.items():
        if samples:
            output.append(f"\n{file}:")
            for sample in samples[:3]:  # Max 3 samples per file
                output.append(f"  {sample}")
    
    return "\n".join(output)

def get_git_diff(force: bool = False) -> Optional[Tuple[str, int]]:
    """Retorna diff processado e número de linhas"""
    start_time = time.time()
    
    if hasattr(get_git_diff, "cache"):
        cache_time, cache_diff, cache_lines = get_git_diff.cache
        if time.time() - cache_time < 2:
            logging.debug("Usando diff do cache")
            return cache_diff, cache_lines
    
    try:
        cmd = [
            "git", "diff", "--cached", 
            "--", ".", 
            ":(exclude).env", 
            ":(exclude)*.env.*"
        ]
        raw_diff = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8")
        
        if not raw_diff.strip():
            logging.warning("Nenhuma alteração no stage. Use 'git add' primeiro.")
            return None, 0
        
        # Conta linhas
        diff_lines = count_diff_lines(raw_diff)
        
        # Se for muito grande e não estiver em modo force, pergunta
        if diff_lines > LARGE_DIFF_THRESHOLD and not force:
            print(f"{Colors.WARNING}⚠️  Large diff detected: {diff_lines} lines changed{Colors.RESET}")
            print(f"{Colors.INFO}This may slow down processing{Colors.RESET}")
            response = input(f"{Colors.INFO}Continue? (y/N): {Colors.RESET}").strip().lower()
            if response != 'y':
                print(f"{Colors.WARNING}Operation cancelled{Colors.RESET}")
                return None, 0
        
        # Parseia inteligentemente baseado no tamanho
        if diff_lines > VERY_LARGE_DIFF_THRESHOLD:
            concise_diff = parse_diff_intelligently(raw_diff, max_lines=30)
        else:
            concise_diff = parse_diff_intelligently(raw_diff, max_lines=50)
        
        concise_diff = sanitize_diff(concise_diff)
        
        if not concise_diff:
            concise_diff = "Modified files (content hidden for security)"
        
        # Guarda no cache
        get_git_diff.cache = (time.time(), concise_diff, diff_lines)
        
        elapsed = (time.time() - start_time) * 1000
        original_size = len(raw_diff)
        new_size = len(concise_diff)
        reduction = ((original_size - new_size) / original_size * 100) if original_size > 0 else 0
        
        logging.debug(f"Diff processed in {elapsed:.1f}ms")
        logging.debug(f"Reduction: {original_size} → {new_size} chars ({reduction:.1f}% smaller)")
        
        return concise_diff, diff_lines
        
    except subprocess.CalledProcessError as e:
        logging.error("Git command failed. Verify this is a valid repository.")
        logging.debug(f"Details: {e.output.decode('utf-8')}")
        return None, 0
    except FileNotFoundError:
        logging.error("Git command not found.")
        return None, 0

# ==========================================
# CLIENTES DE API
# ==========================================
class GroqClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        self.max_context = 8000  # Contexto do Groq

    def generate_commit(self, prompt: str, diff_size: int) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict Git commit message generator. Follow the format EXACTLY as specified. Return ONLY the commit message."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 60,
        }

        try:
            response = self.session.post(self.url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            logging.debug(f"Groq error: {e}")
            return None


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        self.session = requests.Session()
        self.max_context = 32000  # Gemini tem contexto maior

    def generate_commit(self, prompt: str, diff_size: int) -> Optional[str]:
        # Para diffs grandes, aumenta o timeout
        timeout = REQUEST_TIMEOUT
        if diff_size > LARGE_DIFF_THRESHOLD:
            timeout = REQUEST_TIMEOUT * 2
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2,  # Um pouco mais criativo para diffs grandes
                "maxOutputTokens": 100,  # Mais tokens para diffs grandes
                "topP": 0.8,
            }
        }

        try:
            response = self.session.post(self.url, json=payload, timeout=timeout)
            response.raise_for_status()
            
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            logging.debug(f"Gemini error: {e}")
            return None


class DeepSeekClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        self.max_context = 16000

    def generate_commit(self, prompt: str, diff_size: int) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict Git commit message generator. Follow the format EXACTLY as specified. Return ONLY the commit message."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 60,
        }

        try:
            response = self.session.post(self.url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            logging.debug(f"DeepSeek error: {e}")
            return None


class AIClient:
    def __init__(self):
        self.providers = []
        self.stats = {}
        
        # DeepSeek (rápido, médio contexto)
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self.providers.append({
                'name': 'DEEPSEEK',
                'priority_small': 1,  # Prioridade para diffs pequenos
                'priority_large': 2,   # Prioridade para diffs grandes
                'client': DeepSeekClient(deepseek_key, DEFAULT_DEEPSEEK_MODEL)
            })
            self.stats['DEEPSEEK'] = {'avg_time': 0, 'success': 0, 'fails': 0}
        
        # Groq (mais rápido, contexto médio)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.providers.append({
                'name': 'GROQ',
                'priority_small': 1,  # Prioridade para diffs pequenos
                'priority_large': 3,   # Prioridade para diffs grandes
                'client': GroqClient(groq_key, os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL))
            })
            self.stats['GROQ'] = {'avg_time': 0, 'success': 0, 'fails': 0}
        
        # Gemini (mais lento, MAIOR contexto)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            self.providers.append({
                'name': 'GEMINI',
                'priority_small': 3,   # Prioridade baixa para diffs pequenos
                'priority_large': 1,    # Prioridade ALTA para diffs grandes
                'client': GeminiClient(gemini_key, os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL))
            })
            self.stats['GEMINI'] = {'avg_time': 0, 'success': 0, 'fails': 0}
    
    def generate(self, prompt: str, diff_size: int, provider_override: str = None) -> Tuple[Optional[str], str, float]:
        """Gera commit escolhendo o provider baseado no tamanho do diff"""
        
        if provider_override:
            provider_override = provider_override.upper()
            for p in self.providers:
                if p['name'] == provider_override:
                    start = time.time()
                    result = p['client'].generate_commit(prompt, diff_size)
                    elapsed = time.time() - start
                    
                    if result:
                        self._update_stats(p['name'], elapsed, True)
                        return result, p['name'], elapsed
                    else:
                        self._update_stats(p['name'], elapsed, False)
                        return None, p['name'], elapsed
            return None, provider_override, 0
        
        # Escolhe prioridade baseada no tamanho
        is_large = diff_size > LARGE_DIFF_THRESHOLD
        providers_sorted = sorted(
            self.providers, 
            key=lambda x: x['priority_large' if is_large else 'priority_small']
        )
        
        for provider in providers_sorted:
            start = time.time()
            result = provider['client'].generate_commit(prompt, diff_size)
            elapsed = time.time() - start
            
            if result:
                self._update_stats(provider['name'], elapsed, True)
                return result, provider['name'], elapsed
            else:
                self._update_stats(provider['name'], elapsed, False)
                logging.debug(f"{provider['name']} failed in {elapsed:.2f}s")
        
        return None, "NONE", 0
    
    def _update_stats(self, provider: str, elapsed: float, success: bool):
        if provider not in self.stats:
            self.stats[provider] = {'avg_time': 0, 'success': 0, 'fails': 0}
        
        if success:
            self.stats[provider]['success'] += 1
            total = self.stats[provider]['success']
            self.stats[provider]['avg_time'] = (self.stats[provider]['avg_time'] * (total-1) + elapsed) / total
        else:
            self.stats[provider]['fails'] += 1


def build_optimized_prompt(pattern: str, diff: str, diff_size: int, retry_count: int = 0) -> str:
    """Prompt adaptativo baseado no tamanho do diff"""
    
    types = re.findall(r'`(\w+)`:', pattern)
    scopes = re.findall(r'scopes:?\s*(.+?)(?:\n|$)', pattern, re.IGNORECASE)
    
    types_str = ', '.join(types[:10]) if types else 'feat, fix, docs, style, refactor, perf, test, chore'
    scopes_str = scopes[0] if scopes else 'api, ui, db, auth, config, core'
    
    # Para diffs grandes, foca no resumo
    if diff_size > LARGE_DIFF_THRESHOLD:
        prompt = f"""Analyze these changes and generate ONE commit message:

SUMMARY (what changed overall):
{diff}

RULES:
{pattern[:200]}

Based on the summary above, generate a commit message in format:
<type>(<scope>): <subject>

Where:
- type: {types_str}
- scope: {scopes_str} (choose based on main area affected)
- subject: brief, imperative, no caps, no period

Message:"""
    else:
        # Para diffs pequenos, prompt normal
        prompt = f"""Generate commit message:

CHANGES:
{diff}

FORMAT: <type>(<scope>): <subject>
TYPES: {types_str}
SCOPES: {scopes_str}

Message:"""
    
    if retry_count > 0:
        prompt += f"\n\nPrevious suggestion rejected. Try a different approach."
    
    return prompt


def format_time(seconds: float) -> str:
    """Formata tempo de forma legível"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.2f}s"


def display_stats(stats: dict, current_provider: str, response_time: float, total_time: float, diff_size: int):
    """Exibe estatísticas de forma profissional"""
    print(f"\n{Colors.INFO}── Performance ──────────────────────────────{Colors.RESET}")
    print(f"{Colors.GRAY}Provider: {Colors.HIGHLIGHT}{current_provider}{Colors.RESET}")
    print(f"{Colors.GRAY}Diff size: {Colors.HIGHLIGHT}{diff_size} lines{Colors.RESET}")
    print(f"{Colors.GRAY}Response: {Colors.HIGHLIGHT}{format_time(response_time)}{Colors.RESET}")
    print(f"{Colors.GRAY}Total:    {Colors.HIGHLIGHT}{format_time(total_time)}{Colors.RESET}")
    
    if stats:
        successful = [f"{p}({d['success']})" for p, d in stats.items() if d['success'] > 0 and p != current_provider]
        if successful:
            print(f"{Colors.GRAY}History: {', '.join(successful)}{Colors.RESET}")
    print(f"{Colors.INFO}────────────────────────────────────────────{Colors.RESET}")


def validate_commit_message(msg: str, pattern: str) -> Tuple[bool, str]:
    """Valida se a mensagem segue o padrão do commit_pattern.md"""
    if not msg:
        return False, "Empty message"
    
    # Remove qualquer coisa que não seja a mensagem principal
    msg = msg.strip()
    if '\n' in msg:
        msg = msg.split('\n')[0]
    
    types = re.findall(r'`(\w+)`:', pattern)
    types_pattern = '|'.join(types) if types else 'feat|fix|docs|style|refactor|perf|test|chore'
    
    pattern_regex = rf'^({types_pattern})\(([a-zA-Z0-9_-]+)\): (.+)$'
    match = re.match(pattern_regex, msg)
    
    if not match:
        return False, f"Format must be: type(scope): subject"
    
    msg_type, scope, subject = match.groups()
    
    if subject[0].isupper():
        return False, "Subject must not start with capital letter"
    
    if subject.endswith('.'):
        return False, "Subject must not end with period"
    
    if re.search(r'\b(added|changed|fixed|removed|updated)\b', subject.lower()):
        return False, "Use imperative: 'add' not 'added', 'change' not 'changed'"
    
    return True, "OK"


def clean_suggestion(suggestion: Optional[str]) -> Optional[str]:
    """Limpa e valida a sugestão da IA"""
    if not suggestion:
        return None
    
    # Remove aspas e espaços extras
    suggestion = re.sub(r'^["\'`]|["\'`]$', '', suggestion.strip())
    
    # Pega apenas a primeira linha
    lines = suggestion.splitlines()
    if not lines:
        return None
    
    suggestion = lines[0][:MAX_COMMIT_LENGTH]
    
    # Se a mensagem estiver incompleta (ex: "refactor("), tenta extrair algo melhor
    if suggestion.endswith('(') or suggestion.endswith(':') or len(suggestion) < 10:
        # Procura por algo que pareça uma mensagem válida nas linhas seguintes
        for line in lines[1:3]:
            if ':' in line and '(' in line:
                suggestion = line.strip()[:MAX_COMMIT_LENGTH]
                break
    
    return suggestion


# ==========================================
# ORQUESTRADOR PRINCIPAL
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="AI-powered Git commit message generator")
    parser.add_argument("--provider", choices=["groq", "gemini", "deepseek", "auto"], default="auto", 
                       help="Force specific provider (default: auto)")
    parser.add_argument("--model", type=str, help="Override default model")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--pattern", type=str, default="commit_pattern.md", help="Pattern file to use")
    parser.add_argument("--no-color", action="store_true", dest="no_color", help="Disable colors")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark all providers")
    parser.add_argument("--strict", action="store_true", help="Validate message against pattern")
    parser.add_argument("--force", action="store_true", help="Skip large diff confirmation")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(format="%(levelname)s: %(message)s", level=log_level)

    if args.no_color:
        for attr in dir(Colors):
            if not attr.startswith('__'):
                setattr(Colors, attr, '')

    user_start_time = time.time()

    ensure_gitignore()

    # Pega diff e tamanho
    diff, diff_size = get_git_diff(force=args.force)
    if not diff:
        sys.exit(1)

    pattern_path = os.path.join(os.getcwd(), args.pattern)
    try:
        with open(pattern_path, "r", encoding="utf-8") as f:
            pattern = f.read().strip()
            logging.debug(f"Pattern loaded from: {pattern_path}")
    except FileNotFoundError:
        logging.debug(f"File {args.pattern} not found. Using default rules.")
        pattern = """# Commit Rules
1. Format: <type>(<scope>): <subject>
2. Types: feat, fix, docs, style, refactor, perf, test, chore
3. Scopes: api, ui, db, auth, config, core
4. Subject: imperative, no caps, no period"""

    ai_client = AIClient()
    
    if not ai_client.providers:
        print(f"{Colors.ERROR}Error: No API keys found{Colors.RESET}")
        print(f"\n{Colors.WARNING}Configure at least one:{Colors.RESET}")
        print(f"  export DEEPSEEK_API_KEY='your_key'  # Recommended")
        print(f"  export GROQ_API_KEY='your_key'")
        print(f"  export GEMINI_API_KEY='your_key'")
        sys.exit(1)

    if args.benchmark:
        print(f"{Colors.INFO}Benchmark Mode{Colors.RESET}")
        test_prompt = build_optimized_prompt(pattern, diff, diff_size)
        
        for provider in ai_client.providers:
            print(f"\n{Colors.WARNING}Testing {provider['name']}...{Colors.RESET}")
            start = time.time()
            result = provider['client'].generate_commit(test_prompt, diff_size)
            elapsed = time.time() - start
            
            if result:
                cleaned = clean_suggestion(result)
                print(f"{Colors.SUCCESS}  Success in {format_time(elapsed)}{Colors.RESET}")
                print(f"  Message: {cleaned}")
            else:
                print(f"{Colors.ERROR}  Failed after {format_time(elapsed)}{Colors.RESET}")
        
        sys.exit(0)

    retry_count = 0

    while True:
        # Constrói prompt adaptativo
        current_prompt = build_optimized_prompt(pattern, diff, diff_size, retry_count)
        
        if args.debug:
            print(f"{Colors.GRAY}Prompt: {current_prompt[:100]}...{Colors.RESET}")
        
        # Gera sugestão com escolha inteligente de provider
        suggestion, provider_used, response_time = ai_client.generate(
            current_prompt, 
            diff_size,
            args.provider if args.provider != "auto" else None
        )
        
        total_time = time.time() - user_start_time

        if not suggestion:
            print(f"{Colors.ERROR}Failed to generate commit suggestion{Colors.RESET}")
            if args.provider != "auto":
                print(f"{Colors.WARNING}Falling back to auto mode...{Colors.RESET}")
                args.provider = "auto"
                continue
            sys.exit(1)

        # Limpa e valida a sugestão
        suggestion = clean_suggestion(suggestion)
        if not suggestion:
            print(f"{Colors.WARNING}Empty suggestion received, retrying...{Colors.RESET}")
            retry_count += 1
            continue
        
        is_valid, validation_msg = validate_commit_message(suggestion, pattern)

        display_stats(ai_client.stats, provider_used, response_time, total_time, diff_size)
        
        print(f"\n{Colors.SUCCESS}Suggested message:{Colors.RESET}")
        print(f"{Colors.HIGHLIGHT}{suggestion}{Colors.RESET}")
        
        if args.strict and not is_valid:
            print(f"{Colors.WARNING}Warning: {validation_msg}{Colors.RESET}")
        
        print(f"\n{Colors.INFO}Options: [y] confirm | [r] retry | [e] edit | [n] cancel{Colors.RESET}")
        
        try:
            confirm = input(f"{Colors.INFO}→{Colors.RESET} ").strip().lower()
            
            if confirm == 'y':
                commit_start = time.time()
                subprocess.run(["git", "commit", "-m", suggestion], check=True)
                commit_time = time.time() - commit_start
                
                print(f"{Colors.SUCCESS}Commit successful ({format_time(commit_time)}){Colors.RESET}")
                break
                
            elif confirm == 'r':
                retry_count += 1
                print(f"{Colors.INFO}Retrying...{Colors.RESET}")
                continue
                
            elif confirm == 'e':
                manual = input(f"{Colors.INFO}Enter message: {Colors.RESET}").strip()
                if manual:
                    if args.strict:
                        is_valid, msg = validate_commit_message(manual, pattern)
                        if not is_valid:
                            print(f"{Colors.WARNING}Warning: {msg}{Colors.RESET}")
                            proceed = input(f"{Colors.INFO}Commit anyway? (y/N): {Colors.RESET}").lower()
                            if proceed != 'y':
                                continue
                    
                    subprocess.run(["git", "commit", "-m", manual], check=True)
                    print(f"{Colors.SUCCESS}Commit successful{Colors.RESET}")
                break
                
            else:
                print(f"{Colors.WARNING}Cancelled{Colors.RESET}")
                break
                
        except subprocess.CalledProcessError:
            logging.error("Git commit failed")
            break
        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}Cancelled{Colors.RESET}")
            sys.exit(0)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    main()